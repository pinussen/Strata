# Facit och kontroll

Exakta referenssvar finns i `suite.json`, skapad av `build_suite.py` innan svaren
genererades. `check_golds.py` kontrollerar taluppgifterna, räknar ut subnätet med
Pythons `ipaddress`, söker alla heltalsscheman för schemaläggningen och provar
unlink-beteendet på en liten lokal testfil. Resultat: `gold-verification.json`.

`validate.py` kontrollerar kod med fasta och deterministiskt genererade exempel,
samt JSON, CSV, exakt format och ordgränser. Kodgranskning görs före körningen.
Kodtesterna kräver endast Python 3 och skriver i en temporär lokal katalog.
De kör inte genererade driftkommandon eller kontaktar Cisco-servern.

För driftfrågornas manuella facit kontrollerades primärkällor den 7 oktober 2026:

- Öppna, avlänkade filer behålls tills den sista öppna referensen stängs:
  [Linux close(2)](https://man7.org/linux/man-pages/man2/close.2.html).
- `meta: flush_handlers` kör de handlers som då notifierats:
  [Ansible: Handlers](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html).
- Tillståndsadresser kan flyttas från numeriska index till `for_each`-nycklar med
  `moved`-block: [Terraform: Refactor modules](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring).

Systemd-frågans regler står uttryckligen i prompten. Ansible och Terraform
bedöms genom kodgranskning mot dessa dokument; testet skapar ingen infrastruktur.
Språk, nyanser, resonemang och användbarhet bedöms manuellt av Codex med A/B-maskering.
