# Metod och kontroll – konvertering från Stella till Streamlit

Version 1.0, 27 oktober 2026.

## Underlag och avgränsning

Underlaget är användarens två filer: `Klimatmodell CO2e-budget, Avatar-MFF.stmx` och motsvarande `.isdb`. STMX-filen är en XML-fil i XMILE-format från Stella Architect 2.1.5. Den definierar ekvationer, kopplingar, lager, flöden, grafiska funktioner och gränssnitt. ISDB-filen är en SQLite-databas med den sparade simuleringen **Run 1**, 2024–2050.

Översättningen syftar till att återge den befintliga beräkningen i Python och göra den tillgänglig i Streamlit. Inga emissionsfaktorer, klimatbudgetar, åtgärdseffekter eller referenser har uppdaterats. Stella-gränssnittets bilder, sidlayouter, animationer och kontroller med navigeringsfunktioner har ersatts med ett nytt webbgränssnitt.

Källfilens SHA-256 finns i `model/model.json` och i kontrollrapporten. Även ISDB-källan kan spåras genom metadata i `model/reference.json`.

## Modellstruktur

| Egenskap | Antal / värde |
| --- | ---: |
| Unika variabeldefinitioner | 808 |
| Inkopplade alias / externa kopplingar | 127 |
| Oberoende variabler | 681 |
| Oberoende ackumulerande lager | 85 |
| Redigerbara talparametrar | 289 |
| Sparade reglage som överstyr grundekvationer | 51 |
| Unika grafiska definitioner | 24 |
| Grafiska funktioner som inte är alias och kan redigeras direkt | 17 |
| Startår / slutår | 2024 / 2050 |
| Tidssteg | 1/365 år |
| Tidpunkter inklusive start och slut | 9 491 |

Originalet innehåller tre identiska definitioner av samma grafiska variabel för mat. De två upprepningarna har slagits samman utan ändrad funktion. Kopplingarna `connect` och `connect2` i Stella-filens struktur innehåller också upprepningar; 127 unika källkopplingar används. Inkopplade variablers lokala platshållare och alternativvärden ersätts av sin verkliga källvariabel, precis som i den sparade beräkningen.

## Numerisk metod

För varje lager beräknas:

**Lager(t + Δt) = Lager(t) + Δt × [summan av inflöden(t) − summan av utflöden(t)].**

Alla flöden och hjälpvärden för ett tidssteg beräknas innan lagren uppdateras. Variabler beräknas i den ordning som deras beroenden kräver. Lager och flöden med originalets markering för icke-negativa värden behåller den begränsningen. Originalets enda utflödeslager har ingen sådan lagerbegränsning.

Följande konstruktioner hanteras:

- Aritmetik, potenser och jämförelser.
- `IF … THEN … ELSE`, där endast den valda grenen behöver beräknas.
- `INIT`, som bevarar uttryckets värde vid simuleringens start.
- `DELAY`, med fördröjningens startvärde och fasta initiala fördröjningstid. Originalets ROT-fördröjning är 20 år, exakt 7 300 tidssteg.
- `PERCENT(x) = 100 × x`, enligt Stellas funktion. Detta är viktigt för att bevara originalets matberäkningar.
- `EXP` och konstanten `PI`.
- Kontinuerliga grafiska funktioner med linjär interpolation och konstant ändvärde utanför tabellens X-intervall.
- Diskret grafisk funktion för prognosen över antalet elbilar.

Beräkningen körs med dubbelprecision. Tiden beräknas från stegnummer för att begränsa upprepade avrundningsfel. Dagliga beräkningssteg betyder här Δt = 1/365 modellår; det är ingen kalenderdatumberäkning med skottår.

Ekvationer tolkas som ett begränsat uttrycksträd. Den råa Stella-texten körs inte som Python-kod. De genererade beräkningsuttrycken består av kontrollerade operatorer och numeriska variabelindex.

## Startvärden och scenarier

**Sparade reglage i Stella** är standard. Den använder de 51 numeriska överstyrningar som ligger i STMX-filens `controls`-del. Detta alternativ återskapar den bifogade ISDB-körningen.

**Ekvationernas grundvärden** bortser från dessa reglage och använder de underliggande konstantekvationerna. Därför kan resultatet skilja sig betydligt, trots att modellstrukturen är densamma. Båda alternativen har kontrollerats så att alla 808 variabler ger ändliga resultat för sina respektive grundvärden.

Scenariofiler innehåller källmodellens identitet, valt grundscenario, alla 289 talparametrar samt ändrade grafiska kurvor. Appen vägrar läsa in ett scenario från en annan källversion. Det förhindrar att gamla reglage oavsiktligt läggs på en annan modellstruktur.

Stomandelar och kostandelar kontrolleras mot summan 1. Vissa nämnare måste vara större än noll, och Av/På-kontroller måste vara 0 eller 1. Kontrollerna täcker inte alla tänkbara fysiska och metodiska orimligheter.

## Fullständig jämförelse med sparad Stella-körning

Samtliga **681 oberoende variabler** har matchats med motsvarande poster i ISDB-filen. Av dessa är 434 lagrade som konstanta serier med ett värde och 247 lagrade som fullständiga serier med 9 491 värden. Det ger **2 344 711 faktiskt lagrade referensvärden**. Vid jämförelsen kontrolleras även de konstanta värdena över alla beräkningssteg.

För varje tidpunkt gäller godkännandekriteriet:

**|Python − Stella| ≤ 10⁻⁷ + 10⁻⁹ × |Stella|.**

Samtliga jämförelser godkänns. Den största avvikelsen dividerad med seriens största absoluta referensvärde är **7,667 × 10⁻¹⁴**. Alla 808 variabler ger ändliga värden i standardscenariot; inga olösta ekvationer har identifierats.

Detta normaliserade mått ska inte förväxlas med största relativa fel vid varje enskild tidpunkt. Det används som en kompletterande översikt. Godkännandet beräknas punkt för punkt med toleransen ovan. Ingen generell maximal absolut avvikelse är meningsfull när enhet och storleksordning varierar så mycket mellan variablerna.

### Exempel: originalets slutvärden 2050

| Post | ton, enligt originalets CO₂/CO₂e-benämningar |
| --- | ---: |
| Modul 1 | 330 106,709084 |
| Modul 2 | 98 948,044508 |
| Offentliga utsläpp | 62 702,964441 |
| Modul 3 | 170 542,655174 |
| Tilldelad klimatbudget | 14 023,531011 |
| Saldo inklusive offentliga utsläpp | 307 191,531849 |

Klimatbudget dras av vid beräkningen av saldot. En budgettilldelning är därför en redovisningspost i modellen, inte i sig ett negativt utsläpp eller ett upptag av koldioxid.

Fullständig tabell: `docs/kontroll_mot_stella.csv`. Maskinläsbar översikt: `docs/validation_summary.json`.

## Konkret iakttaget i ursprungsmodellen

Följande har bevarats för att översättningen ska kunna kontrolleras mot originalet. De behöver hanteras i en eventuell senare metodrevidering.

1. **Kalenderår som exponent för parklind.** I `Återbetalning.Parklind_omkretstillväxt_(cm/år)` används `… × (1 + tillväxt/100)^TIME`. Kalenderåret 2024 ger redan ett värde omkring 7,6 × 10²². Den efterföljande diametern blir också orimlig. Dessa två hjälpvärden används inte vidare i andra ekvationer som påverkar totalsaldot. I delmodellen Urbana träd finns dessutom en hjälpekvation med exponenten `2023 − TIME`, vilket ger minskande omkrets vid positiv tillväxt. Även dess diameter är en fristående hjälputdata.
2. **Olika tecken i olika summeringar.** `TOTAL.TOTAL` drar av modul 3, medan `TOTAL.Summa_klimatemissioner_i_stadsdel_exkl._personlig_klimatpool_(ton_CO2e)` adderar modul 3. Appens huvudsida använder uttryckligen `TOTAL.TOTAL_inkl._offentliga_utsläpp_(ton_CO2e)` och visar dess beräkningsgång.
3. **Möjlig dubbelräkning i modul 2.** Byggnadernas utsläppssumma innehåller garage och installationer när de är påslagna. Modul 2 adderar också motsvarande ackumulerade garage- och installationsposter separat. Det bör prövas mot avsedd systemgräns innan dessa åtgärder tolkas vetenskapligt.
4. **CO₂ och CO₂e blandas i benämningar.** Den globala budgetens namn, olika utsläppsvariabler och den offentliga sektorns poster använder delvis olika beteckningar. Konverteringen tillför ingen metod för att översätta en fysikalisk CO₂-budget till en generell CO₂e-budget.
5. **Procentetiketter som i praktiken är andelar.** Kostandelarna i Scarborough-delmodellen summerar till 1 trots att namnen anger `%`. Talens ursprungliga innebörd bevaras i gränssnittet och i kontrollen.
6. **Kolinlagring och undvikna utsläpp summeras.** Modul 3 innehåller bland annat biokol, konstruktionsvirke, stadsträd och solel. Dessa poster har olika fysisk innebörd och varaktighet. Appens modulnamn beskriver summeringen i originalet; det är ingen ny bedömning av exempelvis certifiering eller tillåten balansering.
7. **Flera beräkningsspår finns parallellt.** Exempelvis finns flera mobilitets- och matberäkningar. Det är bara de faktiska kopplingarna till slutresultatet som styr totalsaldot. En ändrad hjälpparameter i ett annat spår behöver därför inte ändra huvudresultatet. Variabelns formel och kopplingskälla kan granskas under Delmodeller.

## Testomfattning och kvarvarande verifiering

Elva automatiska tester har körts och godkänts. De täcker den fullständiga referensjämförelsen, körning av grundekvationer, ändrat biokolsscenario, isolerad ändring av emissionskurva, återinläsning av scenarier, indatakontroller samt numerisk funktion för Euler, INIT, DELAY och grafiska funktioner.

Ett separat **Streamlit AppTest** kontrollerar att appen startar, visar det förväntade saldot och kan byta grundscenario. Detta test är medlevererat men kunde inte köras i leveransmiljön, där Streamlit saknas och paketnedladdning är blockerad. Det markeras därför som överhoppat lokalt. GitHub Actions installerar paketen och kör även detta test när projektet finns i GitHub.

En verklig visuell granskning av den startade Streamlit-appen och en faktisk driftsättning är inte genomförda vid leverans. För nya, ändrade scenarier finns ännu ingen separat sparad Stella-referens; vid beslutskritisk användning är stickprov mot Stella lämpliga.

## Tekniska referenser

isee systems (u.å.) *Saving Models*. Tillgänglig: https://iseesystems.org/resources/help/v4/Content/03-BuildingModels/Opening_Closing_Saving/Saving_models.htm (hämtad 27 oktober 2026).

isee systems (u.å.) *Delay builtins*. Tillgänglig: https://iseesystems.org/resources/help/v3/Content/08-Reference/07-Builtins/Delay_builtins.htm (hämtad 27 oktober 2026).

isee systems (u.å.) *Specialized builtins: PERCENT*. Tillgänglig: https://iseesystems.com/resources/help/v4/Content/08-Reference/07-Builtins/Specialized_builtins.htm (hämtad 27 oktober 2026).

isee systems (u.å.) *Graphical Function Tab*. Tillgänglig: https://iseesystems.org/resources/help/v4/Content/08-Reference/01-ObjectsAndProperties/01-BuildingBlocks/07-SharedProperties/Graphical_Function_tab.htm (hämtad 27 oktober 2026).

Streamlit (u.å.) *Deploy your app on Community Cloud*. Tillgänglig: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy (hämtad 27 oktober 2026).

Streamlit (u.å.) *st.testing.v1.AppTest*. Tillgänglig: https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest (hämtad 27 oktober 2026).

De klimatvetenskapliga hänvisningarna i själva Stella-modellen finns kvar som variabeldokumentation i modellunderlaget. De har inte blivit föremål för en ny litteraturgranskning i detta konverteringsuppdrag.
