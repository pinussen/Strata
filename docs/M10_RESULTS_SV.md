# Cisco M10: alla modeller och GPU-antal

Uppdaterad 2026-10-07. Sammanställning av våra sparade mätningar på Cisco-servern.
**Färre GPU:er gav snabbare generering med Q4; fler gav snabbare inläsning av långa frågor.**
Q8 och BF16 har hittills bara mätts med åtta GPU:er. Tomma kombinationer nedan är inte uppskattningar.

Snabblänkar: [testade kombinationer](#testade-kombinationer) · [Strata](#generering-i-strata) ·
[referensmotor](#generering-i-referensmotorn) · [väntetider](#väntetid-till-första-text) ·
[Coder och övriga körningar](#coder-korttester-och-avbruten-körning).

## Längre kontext: Q4 klar, Q8 pågår

Q4 klarar faktakontroller och följdfrågor vid 16K, 32K och 64K, med 65 536 som gemensam
kontextgräns. Svenska svar ger 5,2–5,5 token/s. Ett svenskt 16K-svar blandar ihop postnummer
med stationsnummer; det är ett avgränsat funktionstest, ingen garanti för felfria sammanfattningar.

| Underlag | Q4 första text | Q8 första text | Q4 följdfråga | Q8 följdfråga |
| --- | ---: | ---: | ---: | ---: |
| 14 812 token | 5 min 35 s | 7 min 9 s | 7,4 s | 8,2 s |
| 31 224 token | 11 min 32 s | 14 min 11 s | 7,7 s | 8,3 s |
| 63 960 token | 23 min 45 s | Pågår | 8,3 s | — |

Q8 klarar också faktakontrollerna vid 16K/32K och gav 4,8 token/s i de svenska svaren.
Q8:s 64K-test pågår. [Metod, rådata och aktuella resultat](../bench/results/2026-10-07-cisco-m10-long-context/README.md).
Tabellerna längre ned gäller de tidigare kortkontextmätningarna.

## Maskinen och modellerna

Cisco UCSC-C240-M5SX, två Xeon Gold 6248R, 692 GiB totalt användbart system-RAM enligt värdens
minnesinventering och två fysiska Tesla M10-kort. De innehåller **åtta separata GPU:er med
8 GiB VRAM vardera**. GPU-antal i tabellerna avser dessa kretsar, inte fysiska kort.
VM:en har 24 vCPU; konfigurerat RAM anges per mätserie. CUDA 12.2, SM50.

| Variant av Qwen3.8-Flash-Next | Modellfiler | Omfattning |
| --- | ---: | --- |
| Coder GSQ-RCO IQ1_M | 58,4 GB | Expertbeskuren: 256 experter/lager |
| Full GSQ-RCO IQ3_S | 83,6 GB | Alla 512 experter/lager |
| Full Unsloth UD-Q4_K_XL, kallad Q4 här | 111,3 GB | Full modell, blandad kvantisering |
| Full Unsloth Q8_0 | 188,2 GB | Full modell, högre precision |
| Full Unsloth BF16 | 354,0 GB | Full modell, BF16-variant |

Storlekarna gäller huvudmodellens filer, exklusive separata MTP-filer och packar. Q4, Q8 och
BF16 är samma modell med olika precision. Mer GB innebär inte fler modellparametrar här.

## Testade kombinationer

**Klart** betyder genomförd genereringsmätning; **korttest** är bara enkla funktionskontroller.
**—** betyder att motsvarande kombination inte har mätts. BF16-raden gäller llama.cpp;
full BF16-inferens stöds ännu inte av Strata.

| Modell | 1 GPU | 2 GPU:er | 4 GPU:er | 8 GPU:er |
| --- | --- | --- | --- | --- |
| Coder | Korttest | Korttest | Korttest | Korttest + avbruten längre körning |
| IQ3_S | — | — | Klart | Klart |
| Q4 | Klart | Klart | Klart | Klart, även referensmotor |
| Q8 | — | — | — | Klart i Strata och referensmotor |
| BF16 | — | — | — | Klart i referensmotor |

## Generering i Strata

Token/s för kod, engelska och svenska. Normalt median av två svar med 192 token per svar;
**†** markerar bara ett svar per fall. Speculativt fönster 2, 4 096 kontext, int8 KV,
promptblock 128 och GPU-reserv 1 536 MiB. Svaren når avsiktligt tokenbegränsningen.
Modellnamnen länkar till respektive körnings statistik och rådata finns i samma katalog.

### GPU-jämförelsen: 256 GiB VM-RAM

| Modell | GPU:er | Kod | Engelska | Svenska |
| --- | ---: | ---: | ---: | ---: |
| [IQ3_S](../bench/results/2026-10-05-cisco-m10-large-models/qwen-iq3_s-4gpu-base-ram/summary.json) | 4 | 6,65 | 6,15 | 5,70 |
| [IQ3_S](../bench/results/2026-10-05-cisco-m10-large-models/qwen-iq3_s-8gpu-base-ram/summary.json) | 8 | 6,20 | 5,70 | 5,45 |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-1gpu-confirm-tmpfs/summary.json) | 1 | 7,85 | 7,35 | 6,85 |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-2gpu-base-ram/summary.json) | 2 † | 7,20 | 6,60 | 5,90 |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-4gpu-base-ram/summary.json) | 4 † | 7,10 | 6,60 | 6,00 |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-8gpu-base-ram/summary.json) | 8 | 6,45 | 5,85 | 5,45 |

Q4 med en GPU använder bekräftelsekörningen med två svar per fall. Q4-körningarna saknade
bakgrundsnedladdningar. IQ3-körningarna överlappade modellnedladdning och hade lite observerad
swap; de är utforskande resultat. Alla använde RAM-stagade modellfiler.

### Senare precisionstest: 600 GiB VM-RAM

| Modell | GPU:er | Kod | Engelska | Svenska |
| --- | ---: | ---: | ---: | ---: |
| [Q4](../bench/results/2026-10-06-cisco-m10-q8-bf16/strata-q4-600g/summary.json) | 8 | 6,40 | 5,65 | 5,25 |
| [Q8](../bench/results/2026-10-06-cisco-m10-q8-bf16/strata-q8/summary.json) | 8 | 5,60 | 5,15 | 4,75 |

Två svar per fall, inga nedladdningar och ingen observerad swap under mätningen. Q4 låg i
tmpfs, Q8 i varm NAS-klientcache. Dessa rader är en separat mätserie från 256 GiB-tabellen.
Q8 gav 9–13 % lägre genereringshastighet än Q4 i den här jämförelsen.

## Generering i referensmotorn

**llama.cpp, inte Strata-resultat:** samma motorversion och inställningar för alla tre varianter,
åtta GPU:er, 600 GiB VM-RAM, CPU-experter och PLE, F16 KV, ingen spekulativ generering.
Två svar om 192 token per fall. Dessa siffror ska jämföras inom denna tabell.

| Modell | GPU:er | Kod | Engelska | Svenska |
| --- | ---: | ---: | ---: | ---: |
| [Q4](../bench/results/2026-10-06-cisco-m10-q8-bf16/reference-q4/summary.json) | 8 | 4,76 | 4,77 | 4,74 |
| [Q8](../bench/results/2026-10-06-cisco-m10-q8-bf16/reference-q8/summary.json) | 8 | 4,52 | 4,66 | 4,53 |
| [BF16](../bench/results/2026-10-06-cisco-m10-q8-bf16/reference-bf16/summary.json) | 8 | 2,63 | 2,64 | 2,65 |

Alla tre klarade kodord vid tre promptlängder, räknekontrollen och färdiga svenska/Python-svar.
Varje Python-funktion granskades och passerade samma 107 kontrollfall. Det är inte ett brett
kvalitetstest. Referensmotorn har inte mätts med en, två eller fyra GPU:er i denna jämförelse.

## Väntetid till första text

Sekunder för en fråga där modellen ska hitta ett kodord i en längre prompt. Varje rad bygger
på en körning per promptlängd, utan återanvänd promptcache. **— = inte kört.**

### Strata, 256 GiB VM-RAM, speculativt fönster 2

| Modell | GPU:er | 582 prompttoken | 1 639 prompttoken |
| --- | ---: | ---: | ---: |
| [IQ3_S](../bench/results/2026-10-05-cisco-m10-large-models/qwen-iq3_s-4gpu-base-ram/summary.json) | 4 | 22,05 | 44,31 |
| [IQ3_S](../bench/results/2026-10-05-cisco-m10-large-models/qwen-iq3_s-8gpu-base-ram/summary.json) | 8 | 15,44 | 25,75 |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-1gpu-base-ram/summary.json) | 1 | 59,67 | — |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-2gpu-base-ram/summary.json) | 2 | 43,75 | — |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-4gpu-base-ram/summary.json) | 4 | 31,41 | 66,29 |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-8gpu-base-ram/summary.json) | 8 | 21,98 | 38,18 |

En-GPU-raden här kommer från den första Q4-körningen; bekräftelsekörningen upprepade bara
korta frågor med längre svar. Åtta GPU:er läste dessa längre Q4-promptar snabbare, även om
en GPU genererade svaren snabbare. Vi har inte profilerat den exakta orsaken till skalningen.

I 600 GiB-serien gav Strata med åtta GPU:er **22,95 / 38,52 s för Q4** och
**23,05 / 42,80 s för Q8** vid samma två promptlängder.

### Referensmotor, åtta GPU:er, 600 GiB VM-RAM

| Modell | 582 prompttoken | 1 639 prompttoken | 3 905 prompttoken |
| --- | ---: | ---: | ---: |
| [Q4](../bench/results/2026-10-06-cisco-m10-q8-bf16/reference-q4/summary.json) | 65,05 | 173,88 | 403,17 |
| [Q8](../bench/results/2026-10-06-cisco-m10-q8-bf16/reference-q8/summary.json) | 78,91 | 208,39 | 497,19 |
| [BF16](../bench/results/2026-10-06-cisco-m10-q8-bf16/reference-bf16/summary.json) | 132,36 | 306,69 | 804,81 |

BF16 får alltså plats i minnet, men den längsta frågan tog cirka 13,4 minuter till första text.

## Coder: korttester och avbruten körning

De första testerna använde 128 GiB VM-RAM. Tre enkla frågor gav rätt text med alla GPU-antal.
Hastigheten nedan gäller **ett enda kodsvar på 18 token**, inte 192-tokenstestet ovan.

| GPU:er | Rätt svar | Kod, token/s i korttestet |
| --- | ---: | ---: |
| 1 | 3/3 | 7,4 |
| 2 | 3/3 | 7,4 |
| 4 | 3/3 | 6,7 |
| 8 | 3/3 | 6,5 |

En senare Coder-körning med åtta GPU:er och 256 GiB VM-RAM hann genomföra två 192-tokenssvar
per fall: **6,00 / 5,45 / 4,35 token/s för kod / engelska / svenska**.
Därefter avbröts 582-tokenstestet av watchdog under en NFS-lässtall. Nedladdning pågick
samtidigt. Hela körningen räknas som misslyckad och siffrorna ska inte användas som en ren
GPU-jämförelse. [Avbruten körning](../bench/results/2026-10-05-cisco-m10-large-models/coder-8gpu-base/status.json).

## Övriga uppmätta inställningar

### Speculativt fönster 4, Strata, 256 GiB VM-RAM

Median av två 192-tokenssvar per fall. Jämför med fönster 2 ovan; ändringen hjälpte kodfallet
men försämrade ofta engelska och svenska. IQ3-testerna överlappade nedladdning.

| Modell | GPU:er | Kod | Engelska | Svenska |
| --- | ---: | ---: | ---: | ---: |
| [IQ3_S](../bench/results/2026-10-05-cisco-m10-large-models/qwen-iq3_s-4gpu-spec4-ram/summary.json) | 4 | 7,20 | 5,80 | 5,40 |
| [IQ3_S](../bench/results/2026-10-05-cisco-m10-large-models/qwen-iq3_s-8gpu-spec4-ram/summary.json) | 8 | 6,50 | 5,20 | 4,85 |
| [Q4](../bench/results/2026-10-05-cisco-m10-large-models/unsloth-ud-q4_k_xl-8gpu-spec4-ram/summary.json) | 8 | 6,70 | 5,20 | 4,95 |

Den första Q4-screeningen med **en GPU**, fönster 2 och bara ett 192-tokenssvar per fall gav
**8,10 / 7,70 / 6,90 token/s**. Den upprepade körningens **7,85 / 7,35 / 6,85** används i huvudtabellen.
En mellanliggande omstart misslyckades eftersom den tillfälligt stagade tokenizern hade rensats
vid utloggning; den gav inga inferensvärden. Det åtgärdades med en separat tmpfs-montering.

IQ3 med **åtta GPU:er och promptblock 512** testades bara med en repetition och 32 svarstoken:
**6,10 / 6,00 / 6,00 token/s**. Dessa korta svar jämförs inte med 192-tokenstabellerna.
Prompttakten blev 25,5 respektive 56,8 token/s vid 582/1 639 prompttoken, jämfört med
38,2 respektive 64,2 med promptblock 128. Standardinställningen behölls därför på 128.

## Rapporter, rådata och nuvarande drift

- [Första Coder-/hårdvarutesterna](../bench/results/2026-10-05-cisco-m10/README.md).
- [IQ3, Q4 och GPU-jämförelserna](../bench/results/2026-10-05-cisco-m10-large-models/README.md), inklusive separata livekontroller av Q4-servern.
- [Q4/Q8/BF16 med 600 GiB VM-RAM](../bench/results/2026-10-06-cisco-m10-q8-bf16/README.md).
- [Start/stop och driftinformation](M10_LOCAL_HANDOFF.md).

Q4 körs för närvarande på åtta GPU:er på `http://192.168.3.73:8080`, med befintlig API-nyckel.
Det är en privat LAN-adress; GitHub-tabellen går att läsa från mobilen oberoende av serveråtkomsten.
Q8 ligger kvar på NAS. BF16 ligger tillfälligt i RAM och försvinner vid omstart. Inga nya
benchmarkkörningar har startats för denna sammanställning.
