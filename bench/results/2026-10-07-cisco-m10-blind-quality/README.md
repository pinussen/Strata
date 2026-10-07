# Q4/Q8: blind kvalitetsjämförelse på Cisco M10

**Rekommendation: Q4 som standard.** I denna svenska vardagssvit vann Q4 sex par,
Q8 två, och 24 blev oavgjorda. Q8 gav två konkreta förbättringar men inget
återkommande övertag inom en uppgiftstyp som motiverar en särskild Q8-standard.
Q8:s decode var i genomsnitt 10,8 % långsammare över matchade frågor, och högsta
observerade motor-RSS var 71,8 GiB större. Resultatet visar inte att Q4 alltid
har bättre kvalitet; det ger inget stöd för att betala Q8:s merkostnad som vardagsval.

Körningen gjordes 7 oktober 2026 på Cisco UCS C240 M5SX, Ubuntu VM 104 med
24 vCPU, cirka 590 GiB synligt RAM och åtta Tesla M10-enheter med 8 GiB VRAM
vardera. Q4 är **Unsloth UD-Q4_K_XL**, alltså blandad kvantisering; Q8 är **Q8_0**.
Vi jämför de befintliga Strata-packarna och deras praktiska beteende, inte en
isolerad teoretisk ändring av alla vikter från exakt fyra till åtta bitar.

## Kvalitet

| Mått | Q4 | Q8 |
| --- | ---: | ---: |
| Vinster, 32 par | 6 | 2 |
| Oavgjorda par | 24 | 24 |
| Svar med minst ett kvarstående sakfel | 4 | 5 |
| Namngivna kvarstående sakfel | 7 | 7 |
| Svar med uttryckligen rättad felstart | 3 | 1 |
| Svar med instruktionsbrist eller utelämnat delresultat | 10 | 9 |
| Svar som nådde gränsen 768 token | 3 | 4 |
| Godkända kodtestfall | 273/273 | 273/273 |

Sakfel betyder ett kvarstående falskt påstående någonstans i svaret, även om
slutresultatet är rätt. Rättade felstarter och saknade svar särredovisas, och
påverkar konsistens respektive instruktionsefterlevnad. Antalet namngivna fel är
beroende av hur närliggande fel grupperas; antal svar med fel är lättare att jämföra.
De fullständiga motiveringarna finns i [reviews.json](reviews.json) och
[bedömningsanteckningarna](REVIEW-NOTES.md).

| Fyra frågor per kategori | Q4-vinster | Q8-vinster | Oavgjort |
| --- | ---: | ---: | ---: |
| Kodning/debugging | 0 | 0 | 4 |
| Linux/Ansible/Terraform/systemadministration | 2 | 0 | 2 |
| Teknisk problemlösning | 0 | 1 | 3 |
| Flerstegsresonemang | 2 | 0 | 2 |
| Svenska frågor och skrivuppgifter | 1 | 0 | 3 |
| Detaljinstruktioner | 0 | 0 | 4 |
| Lång kontext | 0 | 1 | 3 |
| Fallgropar | 1 | 0 | 3 |

Q8 var faktiskt bättre i:

- **10, köanalys:** räknade korrekt om 240 jobb/minut till 4 jobb/sekund och fick
  4,5 s i systemet, 3,9 s i kö och 60 % beläggning. Q4 blandade enheter och
  påstod felaktigt att underlaget var motsägelsefullt.
- **26, journal i lång kontext:** valde rätt bokförda poster, hanterade den
  uppdaterade dubbletten och gav 1 400 SEK direkt. Q4 nådde samma slutresultat
  efter ett påhittat kreditvillkor och en felaktig inledning, och överskred ordgränsen.

Q4 vann 05 (du/df), 07 (migrationsordning i Terraform), 13 (schema med två
arbetare), 15 (fler färdiga lagersaldon), 17 (driftmeddelandets detaljer) och 32
(ordgränsen i statistikfrågan). Alla vinster innebär inte ett helt korrekt svar:
07 har brister på båda sidor och 15 är ofullständig på båda sidor. Vinsten i 32
gäller instruktionsefterlevnad, inte bättre förståelse av Simpson-paradoxen.

**28 par har två svar som avslutades utan tokenstopp.** Om de fyra paren med
minst ett avklippt svar (13, 14, 15, 30) tas bort blir utfallet **Q4 4, Q8 2,
oavgjort 22**. Detta är en efterhandskontroll, inte ett nytt huvudtest. Sju av
64 svar tog slut vid tokenbudgeten; framför allt långa, upprepande förklaringar
trängde undan efterfrågade resultat. De kördes inte om. Testet avgör därför inte
vilken modell som är bäst med större svarsmarginal eller aktiverat dolt tänkande.

## Prestanda och minne

| Mått över 32 bedömda körningar per modell | Q4 | Q8 |
| --- | ---: | ---: |
| Decode tok/s, aritmetiskt medel | 6,10 | 5,44 |
| Prompt tok/s, aritmetiskt medel | 14,45 | 15,12 |
| Prompt tok/s, totalt antal token / total prompttid | 20,86 | 21,78 |
| Tid till första synliga token, medel, s | 20,90 | 20,07 |
| Hela svarets tid, medel, s | 67,42 | 70,16 |
| Genererade token per svar, medel | 281,66 | 268,25 |
| Högsta motor-RSS, GiB | 101,50 | 173,29 |
| Minsta tillgängliga gäst-RAM, GiB | 147,79 | 73,66 |
| Högsta observerade swap under frågorna, MiB | 0 | 4,79 |
| Ny swap-in / swap-out under bedömda frågor, byte | 0 / 0 | 0 / 0 |

Medelvärdet av **Q8/Q4-kvoten per fråga** ger −10,76 % för decode-hastighet,
+9,61 % för prompt-hastighet, −7,89 % för TTFT och +2,38 % för hela svarstiden.
Det är en annan sammanvägning än kvoten mellan tabellens medelvärden. Q8 var
alltså inte långsammare på alla latensmått. Olika svarslängder påverkar total tid;
decode tok/s är det tydligare måttet på genereringskostnaden här.

| GPU-index | Q4 högsta VRAM, MiB | Q8 högsta VRAM, MiB |
| --- | ---: | ---: |
| 0 | 7073 | 7184 |
| 1 | 6964 | 7068 |
| 2 | 6958 | 7063 |
| 3 | 6964 | 7068 |
| 4 | 6958 | 7063 |
| 5 | 6961 | 7068 |
| 6 | 6958 | 7063 |
| 7 | 7103 | 7210 |

RAM/RSS, VRAM per GPU, swap, prompt/decode tok/s och TTFT **för varje körning**
finns i [metrics.csv](metrics.csv) och [metrics.json](metrics.json).
Den [sammanfattande tabellen](summary-table.md) förenar parvinnare, sakfel och
hastigheter. Tvåsekunderstelemetrin finns i `unsealed/block-*/telemetry.jsonl`.
Inga telemetrifel registrerades. Toppvärden kan missas mellan provpunkter.

RSS omfattar filbackade sidor och ska inte adderas till filcache. Gästens
`ram_used_bytes` följer den installerade psutil-versionen och motsvarar i dessa
data total minus tillgängligt RAM. BF16:s **329,72 GiB**
tmpfs-filer låg kvar under båda körningarna. Dessa ingår i gästminnet men är
inte Q4:s eller Q8:s modellbehov.

Under Q8:s kallstart ökade swap-out-räknaren med **4 726 784 byte (4,51 MiB)**.
Högst 4,79 MiB swap var allokerad. Räknarna ändrades inte under de 32 bedömda
Q8-frågorna. Vi hävdar därför inte noll swap för hela experimentet. Kall laddning
från NAS tog cirka 1 036 s för Q4 och 1 713 s för Q8 till uppvärmningsfrågan;
dessa tider ingår inte i prompt/decode eller TTFT ovan.

## Metod och reproduktion

Alla 32 prompts är svenska, även programmerings- och driftfrågorna. Fyra frågor
per kategori, längst 2 339 prompttoken, 4 096 tokens kontext och 768 svarstoken.
Temperature 0, seed 20261007, reasoning_effort none. Samma åtta GPU:er,
lagerdelning, prefill 128, spec 2, KV int8, MTP-runtime, 16 pool-workers och
1 536 MiB VRAM-reserv. Båda använde NAS-källor och Stratas RAM-arena/låsta
PLE-tabell. Alla par hade identiska request-payloads och prompttokenantal;
ingen prefixcache återanvändes enligt motorns räknare. En särskild kort
uppvärmning per modell räknas inte som en bedömd fråga.

Modellerna kördes i två sekventiella block, Q4 först efter slumpningen. Detta
balanserar inte tids-/ordningseffekter. Greedy sampling eliminerar samplingsslump,
men en enda körning bevisar inte bitidentisk reproducerbarhet över GPU-processer.
Inga besvarade prompts kördes om.

Facit och protokoll skrevs före svaren. A/B slumpades separat för varje par.
Bedömaren, samma Codex-session som ordnade testet, läste bara de maskerade
svaren och facit, körde granskad Python lokalt och låste samtliga bedömningar
innan A/B-nyckeln öppnades. Det var ingen oberoende mänsklig granskning och
ingen dubbelblind operatörsdesign; detaljerna står i [REVIEW-NOTES.md](REVIEW-NOTES.md).
De 32 valda frågorna och få avgörande paren räcker inte för en generell
kvalitetsranking eller säkra slutsatser om hela uppgiftskategorier.

- [PROTOCOL.md](PROTOCOL.md), [suite.json](suite.json), [FACIT.md](FACIT.md):
  inställningar, alla prompts och frysta facit.
- `blind/01.json`–`blind/32.json`: A/B-texter utan körningsmetadata eller modellidentitet.
- [reviews.json](reviews.json), [automatic-checks.json](automatic-checks.json),
  [review-lock.json](review-lock.json): per-svar-poäng, motiveringar, tester och låsning.
- [mapping-commitment.sha256](mapping-commitment.sha256) och
  [unsealed/mapping.json](unsealed/mapping.json): förhandslåst och sedan öppnad nyckel.
- `unsealed/block-0/` och `unsealed/block-1/`: ursprungliga request/svar-JSON,
  tidsstämplar, SSE-händelsetider, telemetri, konfigurationer och motorloggar.
  API-fältet för modell heter `blind-model`; verkliga packvägar finns separat
  i konfigurationerna och ska inte visas för en ny blind bedömare.
- [metadata/machine.json](metadata/machine.json),
  [metadata/model-files.json](metadata/model-files.json): maskin, byggkonfiguration,
  käll-/binärhashar och befintliga modellfiler. Gästrepositoryt hade egna äldre
  arbetsändringar; dess HEAD ensam identifierar inte den körda motorn.

Lokalt kan kontrollerna reproduceras med Python 3:

```sh
python3 check_golds.py
python3 validate.py --run-reviewed-code
python3 summarize.py
```

Kör dem i denna katalog eller ange skriptens fulla sökvägar. `validate.py` kör
bara de redan manuellt granskade Python-svaren. `summarize.py` kontrollerar
bedömningslåset och nyckelns hash innan det räknar. En ny modellkörning kräver
en **ny arbets-/resultatkatalog**, gästens befintliga modellfiler och venv med
requests/psutil/jinja2. `run_blind.py prepare/run/export/restore` dokumenterar
förloppet men vägrar återanvända de existerande körkatalogerna. Kör inte `run`
igen för att sammanställa dessa resultat. `capture_preflight.py` kontrollerar
kontextlängd och sparar maskinproveniens separat före de bedömda frågorna.

## Ändringar och återställning

Den ursprungliga interaktiva Q4-processen stoppades. Fyra Q4-GGUF-kopior i
`/mnt/strata-ram/data/models/unsloth-ud-q4_k_xl/`, tillsammans 111 334 654 784 byte,
togs bort efter kontroll av befintlig NAS-källa, storlek och källans mtime mot
stagingmanifestet. Detta var **inte** en ny byte-för-byte-hashning. Pack, MTP,
NAS-original, BF16 och systemets permanenta inställningar behölls. Efter varje
modell gavs `POSIX_FADV_DONTNEED` endast på dess NAS-backade GGUF-filer för att
frigöra återställbar filcache.

Varje ändring finns i [metadata/changes.jsonl](metadata/changes.jsonl).
Återställningen kopierar tillbaka Q4 från NAS och återanvänder den ursprungliga
privata serverkonfigurationen inklusive API-skyddet. Slutlig verifierad status
sparas i `metadata/final-access-check.json`; API-nycklar och privata
serverkonfigurationer ingår inte i resultaten. BF16-inventariet före/efter
kontrollerar namn, storlek, mtime och befintliga checksummefiler, inte en ny
fullständig innehållshashning.

**Slutstatus:** Q4 är återställd på `192.168.3.73:8080`. Hälsa och autentiserad
modellista ger HTTP 200; modellistan utan nyckel ger HTTP 401. Ett nytt, separat
funktionsprov svarade `återställd`. Originalkonfigurationen är byte-identisk,
benchmarkport 8097 är stängd och BF16-inventariet är oförändrat. Ingen blockerare
återstår. Den observerade lilla swapmängden och tokenavklippningarna ovan är
mätbegränsningar, inte uteblivna eller påhittade körningar.
