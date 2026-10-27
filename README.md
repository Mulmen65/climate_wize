# Jägersro – klimatmodell i Streamlit

Detta projekt är en första Streamlit-version av **Klimatmodell CO2e-budget, Avatar-MFF**, konverterad från den bifogade Stella Architect-filen. Appen beräknar scenarier för **2024–2050** och kan publiceras från ett GitHub-repository till Streamlit Community Cloud.

**Börja med [PUBLICERA.html](PUBLICERA.html)** för en instruktion utan programmering.

## Vad finns i appen?

- Resultatöversikt med klimatutsläpp, modul 3, klimatbudget och saldo.
- Diagram över tid samt bidrag till det valda årets saldo.
- 289 redigerbara talparametrar, inklusive de 51 sparade Stella-reglagen.
- 17 redigerbara grafiska funktioner. Sju ytterligare grafiska definitioner är kopplade inparametrar; deras värden hämtas från sina källvariabler.
- Både **Sparade reglage i Stella** och **Ekvationernas grundvärden** som startalternativ.
- Utforskning av samtliga 808 variabler, med originalekvationer och dokumentation.
- Export av årsvärden och valda dagliga serier som CSV för svensk Excel.
- Export och återinläsning av scenariofiler med alla talparametrar och ändrade kurvor.
- Inbyggd kontroll mot de sparade resultaten i den bifogade ISDB-filen.

Stella behöver inte vara installerat för att använda eller publicera appen. Den publicerade appen behöver ingen API-nyckel.

## Publicera via GitHub och Streamlit

1. Packa upp zip-filen på din dator. Öppna mappen `klimatmodell_streamlit`.
2. Logga in på [GitHub](https://github.com/new). Skapa exempelvis ett repository med namnet `jagersro-klimatmodell`.
3. Välj **Add file → Upload files**. Dra in **innehållet i projektmappen**, inklusive undermapparna `model`, `docs`, `tests`, `tools`, `.streamlit` och `.github`. Ladda inte bara upp zip-filen.
4. Välj **Commit changes**. Filen `streamlit_app.py` ska finnas direkt i repositoryts rot, tillsammans med `requirements.txt`, `stella_model.py`, `scenario.py` och `validation.py`.
5. Logga in på [Streamlit Community Cloud](https://share.streamlit.io/) med ditt GitHub-konto. Välj **Create app** och därefter alternativet att använda en befintlig app om frågan visas.
6. Välj repository, grenen `main` och **Main file path: `streamlit_app.py`**. I **Advanced settings**, välj **Python 3.12**. Inga secrets behöver fyllas i.
7. Välj **Deploy**. När appen startat får den en adress på `streamlit.app`, som kan delas med andra. Kontrollera delningsinställningen så att önskad målgrupp kan öppna appen.

Om du i stället har lagt hela projektmappen som en undermapp i repositoryt: ange `klimatmodell_streamlit/streamlit_app.py` som startfil. Den medföljande GitHub-kontrollen förutsätter däremot att projektets innehåll ligger i roten.

Officiell anvisning: [Deploy your app on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

## Så använder du modellen

1. Öppna appen. Den startar med **Sparade reglage i Stella**, vilket återger den sparade referenskörningen.
2. Välj vilket år som ska sammanfattas i vänsterspalten. Hela simuleringen körs alltid från 2024 till 2050; årsväljaren ändrar bara presentationen.
3. Öppna **Ändra antaganden**. Ändra i kolumnen **Värde** och välj **Beräkna med dessa värden**. Grundvärdet ligger kvar som jämförelse.
4. Välj **Alla parametrar** för en viss delmodell, eller **Tidskurvor** för att ändra en prognoskurva. Ändringar från andra delmodeller sparas i samma scenario.
5. Kontrollera resultatet. Under **Delmodeller** kan du välja fler variabler, visa deras formler och exportera dagliga beräkningssteg.
6. Välj **Spara scenario (JSON)** för att behålla dina antaganden eller dela dem med en kollega. Filen kan läsas in igen i appen. Sessionens ändringar ligger annars bara kvar medan sessionen består.

Andelar anges normalt som **0–1**, till exempel 0,25 för 25 procent. Originalets benämningar är bevarade; kostandelarna i Scarborough-modellen är ett särskilt fall där namnet anger procent men värdena är andelar. Av/På anges med 0 eller 1. Vid byte mellan betong, stål och trä ska byggnadstypens fem stomandelar tillsammans bli 1.

### Vilket saldo visas?

Översikten använder variabeln `TOTAL.TOTAL_inkl._offentliga_utsläpp_(ton_CO2e)`:

**Saldo = modul 1 + modul 2 + offentliga utsläpp − modul 3 − tilldelad klimatbudget.**

Positivt saldo betyder att den tilldelade budgeten överskrids enligt modellens beräkning. Modul 3 innehåller både kolinlagring och solelens utsläppsreduktion. Tilldelad klimatbudget hålls synlig som en separat post.

## Vad är kontrollerat?

Grundscenariot har jämförts med **alla 681 sparade variabler/tidsserier** i originalets ISDB-fil: **2 344 711 faktiskt lagrade referensvärden**, samt att konstanta serier behåller sina värden under hela perioden. Alla jämförelser är godkända med relativ tolerans `1e-9` och absolut tolerans `1e-7` i respektive variabels enhet.

808 unika variabeldefinitioner och 127 kopplingar ger 681 oberoende beräkningsvariabler. De 85 oberoende lagren uppdateras med Euler-metoden och samma tidssteg som i originalet, **1/365 år**. 9 491 tidpunkter ingår inklusive start och slut.

Den största avvikelsen dividerad med respektive referensseries största belopp är cirka **7,7 × 10⁻¹⁴**. För vissa orimligt stora hjälpvärden i originalet blir den absoluta avrundningsskillnaden stor, trots att den relativa skillnaden är mycket liten. Kontrolltabellen visar båda måtten.

**Begränsning vid leverans:** beräkningsmotor och scenarier har körts och kontrollerats i Python 3.12.14 med NumPy 2.3.5. Elva automatiska tester har godkänts. Det faktiska Streamlit-starttestet kunde inte köras i leveransmiljön eftersom Streamlit saknas och paketnedladdningen blockeras. Testet följer med och körs automatiskt i GitHub Actions när projektet laddas upp. Den publicerade appens start och visuella utseende ska därför verifieras vid driftsättning.

Kontrollen gäller återgivningen av den bifogade modellen. Den är ingen oberoende vetenskaplig validering av modellens systemgränser, faktorer eller klimatbudget. Se [metod och kontroll](docs/METOD_OCH_KONTROLL.md) för konkreta iakttagelser i originalet.

## Filer som behöver följa med

| Fil eller mapp | Funktion |
| --- | --- |
| `streamlit_app.py` | Appens startfil och användargränssnitt |
| `stella_model.py` | Modelläsare, ekvationstolk och beräkningsmotor |
| `scenario.py` | Scenarier och indatakontroller |
| `validation.py` | Kontroll mot originalresultat |
| `requirements.txt` | Versionsbestämda Python-paket |
| `model/model.json` | Originalets ekvationer, kurvor, dokumentation och sparade reglage |
| `model/reference.json`, `model/reference.npz` | Referensresultat extraherade ur ISDB-filen |
| `.streamlit/config.toml` | Appens utseende och inställningar |
| `docs/` | Metodbeskrivning och kontrollresultat |
| `tests/` | Numeriska tester och Streamlits starttest |
| `tools/` | Konvertering och förnyad referenskontroll |
| `.github/workflows/test.yml` | Automatisk kontroll i GitHub |

De ursprungliga STMX- och ISDB-filerna behövs inte i repositoryt. Underlaget är redan extraherat. Lokala Excel-exportvägar, bilder, animationer och den ursprungliga Stella-layouten ingår inte i appens modellunderlag.

## Lokal körning – endast om du vill

Öppna en terminal i projektmappen och kör:

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Kontroller:

```bash
python -m unittest discover -s tests -v
python tools/validate_model.py
```

`validate_model.py` uppdaterar `docs/validation_summary.json` och `docs/kontroll_mot_stella.csv`.

## Uppdatera efter en ändring i Stella

En utvecklare kan extrahera en ny version med:

```bash
python tools/import_stella.py "ny_modell.stmx" --isdb "ny_modell.isdb"
python tools/validate_model.py
python -m unittest discover -s tests -v
```

Konverteraren är anpassad till konstruktionerna i denna modell. Nya funktioner eller ändrade variabelnamn kan kräva kodändringar, kontroll av referenskörningen och justering av gränssnittet. En uppdaterad Stella-fil blir därför inte automatiskt en verifierad ny app. Start- och slutår är dessutom fast presenterade som 2024–2050 i denna appversion.

App och projekt är förberedda för publicering. Ingen driftsättning i användarens GitHub- eller Streamlit-konto har genomförts vid leveransen.
