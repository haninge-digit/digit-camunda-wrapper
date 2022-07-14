# Camunda wrapper
Camunda har en fast uppsättning API'er som visserligen är omfattande och funktionella men som alltid inte är enkla att förstå och använda.
För detta ändamål så "wrappar" vi Camunda med en uppsättning lättanvända API'er. Dock behöver API'er vara generiska så att det inte behöver ändras t.ex. beroende på vilket formulär som fyllts i eller vilken verksamhetsprocess som är involverad.

### Beta-API'er
För att kunna testa nya och uppdaterade API'er utan att störa befintliga, finns dessa under egna (och tillfälliga) URL'er.
Beta-API'erna är identiska sånär som på att dessa börjar med "/beta", t.ex.
```
curl -X POST -d '<JSON-struct>' -H "Content-Type: application/json" https://<camunda-url>/beta/form/process/<process-name>/ 
```
När API'et tas i produktion, tas "/beta" bort.


## Skicka in formulär

```
curl -X POST -d '<JSON-struct>' -H "Content-Type: application/json" https://<camunda-url>/form/process/<process-name>/ 
```
eller
```
curl -X POST -d '<formdata>' -H "Content-Type: "application/x-www-form-urlencoded" https://<camunda-url>/form/process/<process-name>/ 
```

Ett POST-anrop startar angiven process och skickar parametrarna (nycklar och värden) med den bifogade JSON- eller formsstruktur i startanropet. Anropet är skapat för fomulär där data skickas in och inget data förväntas tillbaka. API'et fungerar “out-of-the-box" för EpiForms.

JSON/formuläret innehåller nycklar och värden för resp. fält i formuläret och läggs in som parametrar vid anropet av angiven process. Alla värden förutsätts vara textsträngar. 

Alla nycklar och värden kommer att läggas in som parametern "variables" enligt https://docs.camunda.org/manual/7.5/reference/rest/process-definition/post-start-process-instance/#request-body  

Anropet returnerar 200 vid OK. De flesta andra returkoder kommer från Camunda och anges med "Camunda error", t.ex. 404 som innebär att angiven process inte finns.


## Processanrop utan returvärde

Detta anrop startar en utpekad process i Camunda. Anropssturkturen är namnet på processen anges i URL’en i anropet och måste matcha exakt.

```
curl -X [POST,PUT] [-d '<JSON-struct>' -H "Content-Type: application/json"] https://<camunda-url>/process/<process-name>?<query args>
```

Det enda standardiserade värdet i anropet är "userid" som anger användarID på en ev. inloggad användare. Anonyma användare anges med en tom sträng. 

"query args" kommer att läggas in som separata variabler till Camunda processen. JSON-strukturen kommer att läggas in som en parameter med namnet "JSON_BODY".
Anropsmetoden läggs in som parametern "HTTP_METHOD" och namnet på den anropade processen som "PROCESS_NAME".

Mer info fins på https://docs.camunda.org/manual/7.5/reference/rest/process-definition/post-start-process-instance/#request-body  

Om processen startar returneras bara "200". Andra returkoder kommer från Camunda och anges med "Camunda error", t.ex. 404 som innebär att angiven process inte finns.

## Processanrop med returvärde

Detta anrop startar en utpekad process i Camunda. Anropssturkturen är namnet på processen anges i URL’en i anropet och måste matcha exakt.

```
curl -X GET [-d '<JSON-struct>' -H "Content-Type: application/json"] https://<camunda-url>/process/<process-name>?<query args>
```
Det enda standardiserade värdet i anropet är "userid" som anger användarID på en ev. inloggad användare. Anonyma användare anges med en tom sträng. 

"query args" kommer att läggas in som separata variabler till Camunda processen. JSON-strukturen kommer att läggas in som en parameter med namnet "JSON_BODY".
Anropsmetoden läggs in som parametern "HTTP_METHOD" och namnet på den anropade processen som "PROCESS_NAME".

Mer info fins på https://docs.camunda.org/manual/7.5/reference/rest/process-definition/post-start-process-instance/#request-body  

Ett GET-anrop syftar till att starta en process som skapar ett specifikt resultat. Resultatet returneras och processen i Camunda avslutas. Alla parametrar i anropet skickas som strängparametrar till processen.  

I ett steg i processen hämtas alla befintliga parametrar och returneras som en JSON-struktur från detta anrop. Steget i processen är ett "User task" ock ska heta “**GET response**"

Om processen löpts igenom returneras "200" tillsammans med en JSON-struktur som hämtas från processsteget “**GET response**". Om detta processsteget saknas eller om processen fastnar före detta processsteg, kommer GET-anropet att så smånigom "tajma" ut.

Andra returkoder kommer från Camunda och anges med "Camunda error", t.ex. 404 som innebär att angiven process inte finns.

