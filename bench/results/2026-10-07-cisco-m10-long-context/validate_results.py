"""Check the two completed protocols and export their per-request metrics.

This validates measurement integrity and exact retrieval, not summary semantics.
Run after summarize_context.py has generated both completed summaries.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    runs = {}
    configurations = {}
    checks = {}
    csv_rows = []
    expected_cases = {'warmup'} | {f'{size}k/{case}' for size in (16, 32, 64)
        for case in ('cold_retrieval', 'cached_inventory', 'cached_swedish')}
    for model in ('q4', 'q8'):
        path = ROOT / f'{model}-64k'
        status = json.loads((path / 'status.json').read_text())
        config = json.loads((path / 'config.json').read_text())
        summary = json.loads((path / 'summary.json').read_text())
        assert status['state'] == summary['state'] == 'complete', model
        assert not config.get('api_key'), 'Do not archive credentials'
        assert config['gpu'] == list(range(8)), config['gpu']
        normalized = json.loads(json.dumps(config))
        for key in ('model_name', 'tokenizer', 'log'):
            normalized.pop(key, None)
        for flag in ('--native', '--pack'):
            normalized['args'][normalized['args'].index(flag) + 1] = '<model-specific-path>'
        configurations[model] = normalized
        args = config['args']
        flags = {flag: args[args.index(flag) + 1] for flag in (
            '--max-context', '--kv', '--prefill', '--spec', '--pool-workers', '--vram-reserve-mib')}
        assert flags == {'--max-context': '65536', '--kv': 'int8', '--prefill': '128',
                         '--spec': '2', '--pool-workers': '16', '--vram-reserve-mib': '1536'}, flags
        rows = [json.loads(line) for line in (path / 'requests.jsonl').read_text().splitlines()]
        assert len(rows) == len(expected_cases) and {r['case'] for r in rows} == expected_cases
        runs[model] = {r['case']: r for r in rows}
        for row in rows:
            name, timing, usage = row['case'], row['final']['timings'], row['final']['usage']
            assert row['token_count_matches'] and row['counted_prompt_tokens'] == usage['prompt_tokens']
            assert row['finish_reason'] in ('stop', 'length')
            assert timing['cache_n'] + timing['prompt_n'] == usage['prompt_tokens']
            assert usage['prompt_tokens'] + row['request']['max_tokens'] <= 65536
            if name.endswith('cold_retrieval'):
                assert timing['cache_n'] == 0
                target = int(name.split('k/')[0]) * 1024
                assert target - 1600 <= usage['prompt_tokens'] <= target - 1536
            if name == 'warmup':
                continue
            observed = summary['cases'][name]['telemetry']
            csv_rows.append({
                'model': model.upper(), 'gpus': 8, 'capacity': 65536, 'case': name,
                'prompt_tokens': usage['prompt_tokens'], 'cached_tokens': timing['cache_n'],
                'new_prompt_tokens': timing['prompt_n'], 'completion_tokens': usage['completion_tokens'],
                'first_text_s': round(row['first_token_s'], 3), 'whole_reply_s': round(row['wall_s'], 3),
                'prompt_tok_s': timing['prompt_per_second'], 'decode_tok_s': timing['predicted_per_second'],
                'finish_reason': row['finish_reason'], 'exact_json_correct': row.get('correct', ''),
                'max_engine_rss_gib': round(observed['max_engine_rss_gib'], 3),
                'min_available_ram_gib': round(observed['min_available_ram_gib'], 3),
                'max_gpu_used_mib': max(observed['gpu_max_used_mib'].values()),
                'max_gpu_temperature_c': max(observed['gpu_max_temperature_c'].values()),
            })
    assert configurations['q4'] == configurations['q8'], 'Unexpected configuration difference'
    for name in sorted(expected_cases):
        q4, q8 = runs['q4'][name], runs['q8'][name]
        p4, p8 = q4['request'], q8['request']
        for key in ('temperature', 'reasoning_effort', 'max_tokens'):
            assert p4[key] == p8[key], (name, key)
        user4 = [m for m in p4['messages'] if m['role'] != 'assistant']
        user8 = [m for m in p8['messages'] if m['role'] != 'assistant']
        assert user4 == user8, name
        if name.endswith('cold_retrieval') or name == 'warmup':
            assert p4['messages'] == p8['messages']
            assert q4['counted_prompt_tokens'] == q8['counted_prompt_tokens']
        checks[name] = {
            'same_system_and_user_messages': True,
            'identical_all_messages': p4['messages'] == p8['messages'],
            'same_prompt_token_count': q4['counted_prompt_tokens'] == q8['counted_prompt_tokens'],
            'identical_generated_text': q4['content'] == q8['content'],
            'system_and_user_sha256': hashlib.sha256(json.dumps(user4, ensure_ascii=False,
                sort_keys=True).encode()).hexdigest(),
        }
    word_counts = {model: {name: len(row['content'].split()) for name, row in rows.items()
                  if name.endswith('cached_swedish')} for model, rows in runs.items()}
    result = {'protocol_checks_pass': True, 'requests_per_model': len(expected_cases),
              'retrieval_checks_passed_per_model': {model: sum(row.get('correct') is True
                  for name, row in rows.items() if name.endswith(('cold_retrieval', 'cached_inventory')))
                  for model, rows in runs.items()},
              'retrieval_checks_total_per_model': 6,
              'all_replies_completed_normally': {model: all(row['finish_reason'] == 'stop'
                  for row in rows.values()) for model, rows in runs.items()},
              'all_followups_reused_over_99_percent': {model: all(row['final']['timings']['cache_n'] >
                  row['final']['usage']['prompt_tokens'] * .99 for name, row in rows.items()
                  if 'cached_' in name) for model, rows in runs.items()},
              'comparison': checks,
              'swedish_word_counts_whitespace': word_counts,
              'quality_scope': 'Exact JSON retrieval and completion are checked automatically. See manual-review.json for semantic errors; word-count misses remain visible.'}
    (ROOT / 'protocol-validation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    with (ROOT / 'metrics.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(json.dumps({'protocol_checks_pass': True, 'requests_per_model': len(expected_cases),
                      'csv_rows': len(csv_rows), 'swedish_word_counts': word_counts}, ensure_ascii=False))


if __name__ == '__main__':
    main()
