import sys
import codecs
if sys.platform.startswith("win"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

import text_parser

text = """piecz dü firmy	Faktura VAT àódi	Nr FV 0861/25/LD	
2025-10-07 ódi	2025-10-07	
data i micisce wystawienia dokumentu	data sprzedaly	
Sprzedawca: "NATURAL" Sáawomir Walczak,	Nabywca: Hanna Herasimava	
ariaAntoniewska-Banach Sp.	Adres: 04-161 Warszawa, Komorska 29/33/12	
dres: 90-558 aódi, ul. 28 Puáku Strzelco	NIP: 1133144313	
Kaniowskich 67 NIP: 725-002-15-38	
Forma pátno Gci: przedpáata	dbiorca: Hanna Herasimava	
Termin pátnoeci: 2025-10-07	dres: 04-161 Warszawa, Komorska 29/33/1	
ank: Santander Bank Polska S.	
onto: 89 1090 1304 0000 0000 3000 29*	
556 2052 - 170 199 - 168	
Lp.	Nazwa	loeu	Jm	Cena	Wartoeu	Stawka	Kwota	Wartoeu	
netto	netto	VAT	VAT	brutto	
1	Tiul 556 170 czamy	5mb	14,00	210,00	23%	48,30	258,30	
2	Microfibra 199 168 silver	5 mb	19,40	291,00	23%	66,93	357,93	
3	Mikrofibra 2052 170 czarny	5 mb	27,30	409,50	23%	94,19	503,69	
4	koszty wysyáki	1 szt	35,79	35,79	23%	8,23	44,02	
RAZEM,	946,29	217,65	1 163,94	
W tym	946,29	23%	217,65	1 163,94	
Razem do zapáaty: 1 163,94 PLN	Pozosta3o do zapáaty: 1 163,94 PLN	
Gáownie: jeden tysiąc sto szeGúdziesiat trzy záote dziewiCúdziesiat cztery grosze	
W sumie rabat	Netto	
0,00%	0,00"""

print(text_parser.parse_invoice_text(text))
