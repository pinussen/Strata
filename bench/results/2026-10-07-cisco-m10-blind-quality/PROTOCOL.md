# Förhandsbestämt protokoll

Syfte: välja vardagsmodell på Cisco M10 genom att jämföra den befintliga Unsloth
UD-Q4_K_XL-modellen med Q8_0 i samma Strata-motor. Detta är en lokal uppgiftssvit,
inte ett representativt populationsurval eller ett test av alla kvantiserare.

32 olika uppgifter, fyra i var och en av åtta kategorier. `suite.json` innehåller
exakt prompt, kategori, facit och kodtestdata. Facit skrevs före generering.
Varje prompt skickas exakt en gång per modell. Inga omkörningar planeras; en
eventuell extra körning måste motiveras separat och ersätter aldrig originalsvar.

Temperature 0 (greedy), seed 20261007, reasoning_effort none, max_tokens 768,
4096 kontext, åtta GPU:er, samma lagerdelning, KV int8, prefill 128, spec 2,
spec-min-p 0.5, 16 CPU pool-workers, VRAM-reserv 1536 MiB, samma MTP-runtime.
Ingen konversationshistorik mellan uppgifter. Systemprompten är identisk mellan
modeller för samma uppgift och innehåller ett uppgifts-id för att begränsa delad
prefixcache. Faktiskt återanvända token sparas i motorns timings.
Temperature 0 eliminerar samplingsslump; GPU-beräkningar garanteras inte vara
bitidentiska mellan alla processstarter. Det prövas inte med rutinmässiga repetitioner.

Modeller körs sekventiellt, med slumpad blockordning för att rymmas i RAM/VRAM.
En separat, kort uppvärmningsfråga per modell ingår inte i kvalitetsresultatet.
Alla 32 frågor körs i samma ordning inom respektive block. Ordningseffekter inom
block och variation över tid kan inte uteslutas med en körning per fråga.

A/B slumpas oberoende per uppgift. Körverktyget sparar modellkopplingen separat
utanför repositoryt och låser den med SHA256 före generering. Granskaren får
endast parens text, prompt och facit, utan timings, filnamn som identifierar
modell, blocknummer eller ordningsnyckel. Granskningen görs av samma Codex-session
som förberedde testet, i ett separat bedömningssteg, inte av en oberoende människa.
Bedömningen låses med SHA256 innan kopplingen öppnas. Att en bedömare känner till
testets modeller innebär att detta är maskerad parbedömning, inte dubbelblind
klinisk metodik.

Varje svar bedöms 0–2 på korrekthet, instruktionsefterlevnad, resonemang/konsistens,
frånvaro av hallucinationer/felaktiga antaganden, samt praktisk användbarhet.
Kodkvalitet får 0–2 för koduppgifterna, annars null. 2 betyder uppfyllt, 1 en
begränsad brist, 0 en väsentlig brist. Vinnare bestäms av praktisk användbarhet
med korrekthet och bindande instruktioner först. Enbart längd eller stil räcker
inte för vinst. Likvärdiga användbara svar blir oavgjorda.

Objektiva fel redovisas både som antal svar med minst ett verifierat fel och som
namngivna fel per svar. Format- och längdbrott särredovisas; de räknas inte som
sakfel. Kod som saknar begärd funktion eller returnerar fel räknas som sakfel.
Svårtolkade fall förklaras i bedömningen. Avklippta svar sparas och markeras.

Python-kod inspekteras före exekvering och testas i separat process med tids- och
resursgränser, utan serveråtkomst eller hemligheter. Övriga facit kontrolleras
med aritmetik, parser eller manuell granskning. Inga genererade driftkommandon
körs på Cisco-servern.

Motorns prompt/decode tok/s och klientens tid till första text-/reasoning-delta
sparas per förfrågan. TTFT är därmed synlig första-token-latens, inte en intern
GPU-tidsstämpel. RAM/RSS, swap och VRAM per GPU samplas varannan sekund. RSS
inkluderar filbackade sidor och ska inte adderas till systemets cache. RAM-tabellen
skiljer totalt gästminne/använt/tillgängligt från process-RSS. BF16:s kvarvarande
tmpfs-filer ingår i systemets RAM men är inte den körda modellens minnesbehov.

Prestanda jämförs över matchade uppgifter, både med medelvärde av per-par-kvoter
och sammanvägd token/tid. Svarslängder kan skilja sig; totalsvarstid mäter därför
även hur mycket modellen skriver. Ett enda prov per uppgift ger inga stabila
latenspercentiler eller bevis för generella kvalitetsskillnader.

BF16-filerna får inte raderas eller ändras. Endast verifierade, NAS-backade
Q4-kopior i tmpfs tas bort inför testet. Samma NAS-källor används för båda modeller.
Ändringarna journalförs, Q4 återställs från NAS och den ursprungliga interaktiva
serverkonfigurationen återanvänds efter testet. Modellkällor och API-nycklar ska
inte committas. BF16-inventariet före/efter jämför filstorlek, mtime och befintliga
checksummefiler; det är inte en ny fullständig hashning av 330 GiB.
