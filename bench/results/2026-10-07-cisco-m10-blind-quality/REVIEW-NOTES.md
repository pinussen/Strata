# Bedömningsanteckningar före avblindning

Granskningen använde bara prompt, fryst facit, A/B-svar och lokala kodtester.
Modellkoppling och prestandadata lästes inte före denna låsning. Ingen separat
mänsklig bedömare eller agent användes. Granskaren känner till att modellerna är
Q4/Q8 och hade under laddningen sett att block 0 använde Q4, men ingen koppling
från A/B per uppgift till block hade lästs. Oberoende slumpning per par behövs
alltså för maskeringen; blockordningen i sig var inte hemlig för operatören.

Objektiva fel avser kvarstående falska sakpåståenden i svaret, även när dess
slutresultat är rätt. Uttryckligen rättade felstarter särredovisas som
`corrected_errors` och sänker konsistens/användbarhet, men räknas inte igen som
kvarstående sakfel. Utelämnade resultat och format-/längdbrott ligger under
`instruction_errors`. Obestyrkta men inte verifierbart falska antaganden noteras
under hallucinationspoängen och i fritext. `final_conclusion_correct=null`
betyder att svaret inte avslutar uppgiften. Dessa preciseringar görs blindat;
samtliga gäller symmetriskt för A/B och låses innan modellnyckeln öppnas.

Numrerade listor i uppgift 19 uppfyller "tre punkter": automatens test för endast
bullet-tecken var för snävt. Den manuella bedömningen åsidosätter just det testet,
men inte det frysta facitet. Python-kodstaket accepteras i 01–04 som normal
kodpresentation; i JSON-uppgifterna där bara JSON efterfrågas räknas kodstaket
som formatbrott. Råsvaret ändras aldrig.

Ord räknas med Python str.split(); uppgift 07 undantar kodblock enligt den
uttryckliga instruktionen "220 ord plus HCL". Kvalitetsvinsterna 15 och 32 är
begränsade: 15 är en mer komplett men fortfarande ofärdig lösning; 32 beror på
bindande längdgräns. Några avklippta svar når korrekta delresultat. Ingen sådan
text fylls i eller får antas ha haft ett korrekt osynligt slut.

Alla åtta kodsvar lästes innan exekvering. Endast funktionsdefinitioner och
standardbiblioteken re, heapq och collections förekommer; inga fil-, nätverks-
eller processanrop finns i svaren. 105+24+40+104=273 testfall per modellarm,
546 totalt, passerar. De ursprungliga källtexterna och deras SHA256 finns i
blindfiler respektive automatic-checks.json. Resursgränserna finns i validate.py.
