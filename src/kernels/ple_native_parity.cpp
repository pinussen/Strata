// Q8_0/BF16 PLE row readers vs ggml, including page crossings and batched/direct reads.
#include "strata/artifact/gguf_reader.hpp"
#include "strata/kernels/ngram.hpp"
#include "ggml.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace k = strata::kernels;
namespace fs = std::filesystem;

template<class T> void put(std::ofstream& f, T v) { f.write(reinterpret_cast<const char*>(&v), sizeof v); }
void put_string(std::ofstream& f, const std::string& s) {
    put<uint64_t>(f, s.size()); f.write(s.data(), s.size());
}
void fixture(const fs::path& p, ggml_type type) {
    constexpr int rows = 513, cols = 160;
    std::vector<float> input(rows * cols);
    for (size_t i = 0; i < input.size(); ++i)
        input[i] = float(int((i * 37) % 8191) - 4095) / float(1 + (i / 160) % 19);
    const size_t bytes = ggml_row_size(type, cols) * rows;
    std::vector<uint8_t> data(bytes);
    if (ggml_quantize_chunk(type, input.data(), data.data(), 0, rows, cols, nullptr) != bytes)
        throw std::runtime_error("fixture quantization size");
    std::ofstream f(p, std::ios::binary);
    put<uint32_t>(f, 0x46554747); put<uint32_t>(f, 3);
    put<uint64_t>(f, 1); put<uint64_t>(f, 0);
    put_string(f, "per_layer_token_embd.weight"); put<uint32_t>(f, 2);
    put<uint64_t>(f, cols); put<uint64_t>(f, rows);
    put<uint32_t>(f, type); put<uint64_t>(f, 0);
    while (static_cast<size_t>(f.tellp()) % 32) put<uint8_t>(f, 0);
    f.write(reinterpret_cast<const char*>(data.data()), data.size());
    if (!f) throw std::runtime_error("fixture write failed");
}

void check(const fs::path& p, bool synthetic, bool mmap_only) {
    auto file = std::make_unique<strata::GgufFile>(p.string());
    const auto* tensor = file->find("per_layer_token_embd.weight");
    if (!tensor || (tensor->type != GGML_TYPE_Q8_0 && tensor->type != GGML_TYPE_BF16) ||
        tensor->shape.size() != 2 || tensor->shape[0] != 160 || tensor->shape[1] < 2)
        throw std::runtime_error("expected Q8_0/BF16 PLE [160, N]");
    const auto type = static_cast<ggml_type>(tensor->type);
    const auto* traits = ggml_get_type_traits(type);
    const auto* data = file->tensor_data(*tensor);
    const size_t rb = ggml_row_size(type, 160);
    const uint32_t last = static_cast<uint32_t>(tensor->shape[1] - 1);
    uint32_t rows[32];
    for (int i = 0; i < 32; ++i) rows[i] = i == 31 ? last : uint32_t(uint64_t(i * 257 + 1) % (last + 1));
    rows[0] = 0; rows[1] = 1;
    std::vector<float> want(32 * 160), got(want.size());
    for (int i = 0; i < 32; ++i) traits->to_float(data + size_t(rows[i]) * rb, want.data() + i * 160, 160);
    file.reset(); // Direct I/O must not compete with a second live mapping of the same file.
    auto equal = [&] (const char* label, const float* values, size_t count) {
        for (size_t i = 0; i < count; ++i)
            if (!std::isfinite(values[i]) || !std::isfinite(want[i]) || values[i] != want[i])
                throw std::runtime_error(std::string(label) + ": reference mismatch at " + std::to_string(i));
    };
    k::PleTable table;
    for (int arm = 0; arm < (synthetic ? 3 : 2); ++arm) {
        if (mmap_only && arm == 1) continue; // tmpfs does not support O_DIRECT
        const auto mode = arm == 1 ? k::PleIo::Direct : k::PleIo::Mmap;
        k::PleIoOptions options; options.mode = mode; options.cache_rows = 64;
        options.lock = arm == 2; // only lock the tiny synthetic table, not a 102 GB real shard
        std::string err;
        if (!table.open(p.string(), err, options)) throw std::runtime_error(err);
        if (options.lock && !table.locked()) throw std::runtime_error("synthetic table was not locked");
        if (std::strcmp(table.format(), type == GGML_TYPE_Q8_0 ? "Q8_0" : "BF16"))
            throw std::runtime_error("format reporting mismatch");
        for (int i = 0; i < 32; ++i) table.read_row(rows[i], got.data() + i * 160);
        equal("read_row", got.data(), got.size());
        if (!table.issue(rows) || !table.collect(got.data(), err)) throw std::runtime_error("collect: " + err);
        equal("issue/collect", got.data(), 16 * 160);
        for (int i = 0; i < 2; ++i) table.prefetch_rows(rows + i * 16);
        if (!table.gather_batch(rows, 2, got.data(), err)) throw std::runtime_error("prefetch/gather: " + err);
        equal("prefetch/gather", got.data(), got.size());
        if (!table.gather_batch(rows, 2, got.data(), err)) throw std::runtime_error("gather: " + err);
        equal("gather", got.data(), got.size());
        std::printf("%s %s: 32 probe rows, single/collect/prefetch/batch exact PASS\n",
                    table.format(), arm == 1 ? "direct" : arm == 2 ? "locked mmap" : "mmap");
        table.close();
    }
}

int main(int argc, char** argv) {
    fs::path dir;
    try {
        const bool mmap_only = argc > 1 && std::string(argv[1]) == "--mmap-only";
        const int first = mmap_only ? 2 : 1;
        if (argc == first + 1 && std::string(argv[first]) == "--selftest") {
            dir = fs::temp_directory_path() / ("strata-ple-native-" + std::to_string(
                std::chrono::steady_clock::now().time_since_epoch().count()));
            if (!fs::create_directory(dir)) throw std::runtime_error("cannot create fixture directory");
            for (auto type : {GGML_TYPE_Q8_0, GGML_TYPE_BF16}) {
                const auto p = dir / (std::to_string(int(type)) + ".gguf");
                fixture(p, type); check(p, true, mmap_only);
            }
            fs::remove_all(dir);
        } else if (argc > first) {
            for (int i = first; i < argc; ++i) check(argv[i], false, mmap_only);
        } else { std::fprintf(stderr, "usage: ple_native_parity [--mmap-only] --selftest | PLE-shard.gguf ...\n"); return 2; }
    } catch (const std::exception& e) {
        if (!dir.empty()) fs::remove_all(dir);
        std::fprintf(stderr, "FAIL: %s\n", e.what()); return 1;
    }
    return 0;
}
