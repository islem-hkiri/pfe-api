/* ESP32 Firmware - VERSION RENDER (HTTPS)
   Communication avec API Flask hébergée sur Render
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h> // ⚠️ Nouveau pour le HTTPS

// ================= CONFIGURATION WIFI =================
const char* ssid = "Infinix HOT 30"; [cite: 1]
const char* password = "chaima123"; [cite: 2]

// ================= CONFIGURATION RENDER =================
// ⚠️ REMPLACE PAR TON LIEN RENDER SANS "https://"
const char* serverHost = "pfe-api-bwtn.onrender.com"; 
const int serverPort = 443; // Port standard pour HTTPS

// ================= PINS =================
const int PIN_LIMIT_SWITCH = 32; [cite: 7]
const int PIN_CANCEL_BUTTON = 12; [cite: 7]
const int PIN_LED_ROUGE = 14; [cite: 8]
const int PIN_LED_ORANGE = 27; [cite: 8]
const int PIN_LED_VERTE = 26; [cite: 8]

// ================= VARIABLES =================
String currentShift = "B"; [cite: 9]
bool productionEnCours = false; [cite: 10]
int compteurLocal = 0; [cite: 10]
int quantiteMax = 0; [cite: 10]
int demandeId = 0; [cite: 10]
int erreurConsecutive = 0; [cite: 11]
const int MAX_ERREURS = 5; [cite: 11]

unsigned long lastDebounceTime = 0; [cite: 12]
const unsigned long debounceDelay = 100; [cite: 12]
bool lastLimitState = HIGH; [cite: 12]
bool lastCancelState = HIGH; [cite: 12]

unsigned long lastLEDUpdate = 0; [cite: 13]
const unsigned long LED_UPDATE_INTERVAL = 10000; // ⚠️ Augmenté à 10s pour Render (économie de ressources)

unsigned long dernierIncrement = 0; [cite: 14]
const unsigned long TIMEOUT_PRODUCTION = 300000; [cite: 14]

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LIMIT_SWITCH, INPUT_PULLUP); [cite: 16]
  pinMode(PIN_CANCEL_BUTTON, INPUT_PULLUP); [cite: 16]
  pinMode(PIN_LED_ROUGE, OUTPUT); [cite: 16]
  pinMode(PIN_LED_ORANGE, OUTPUT); [cite: 16]
  pinMode(PIN_LED_VERTE, OUTPUT); [cite: 16]
  
  setLED(LOW, LOW, LOW); [cite: 16]

  WiFi.begin(ssid, password); [cite: 17, 18]
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print("."); [cite: 18]
  }
  Serial.println("\n✅ WiFi Connecté!"); [cite: 19]

  mettreAJourEtatDepuisAPI(); [cite: 21]
}

// ================= LED CONTROL =================
void setLED(bool rouge, bool orange, bool verte) {
  digitalWrite(PIN_LED_ROUGE, rouge ? HIGH : LOW); [cite: 23]
  digitalWrite(PIN_LED_ORANGE, orange ? HIGH : LOW); [cite: 23]
  digitalWrite(PIN_LED_VERTE, verte ? HIGH : LOW); [cite: 24]
}

// ================= APPEL API (HTTPS) =================
int appelAPI(String endpoint, String method, String body, String &response) {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect(); [cite: 28]
    return -1;
  }

  WiFiClientSecure *client = new WiFiClientSecure;
  if(client) {
    // ⚠️ On ignore la vérification du certificat pour simplifier (Insecure)
    client->setInsecure(); 
    
    HTTPClient http;
    String url = "https://" + String(serverHost) + endpoint; [cite: 29]
    
    http.begin(*client, url);
    http.addHeader("Content-Type", "application/json"); [cite: 30]

    int httpCode;
    if (method == "GET") httpCode = http.GET(); [cite: 31]
    else httpCode = http.POST(body); [cite: 32]

    if (httpCode > 0) {
      response = http.getString(); [cite: 33]
      erreurConsecutive = 0; [cite: 36]
    } else {
      Serial.printf("❌ Erreur HTTPS: %s\n", http.errorToString(httpCode).c_str());
      erreurConsecutive++; [cite: 37]
    }

    http.end();
    delete client;
    return httpCode; [cite: 38]
  }
  return -1;
}

// ================= REST LOGIC (Identique au précédent) =================
// [Les fonctions mettreAJourEtatDepuisAPI, lancerProduction, incrementerProduction, 
//  decrementerProduction, gererPedale, gererAnnulation restent les mêmes logic]

void mettreAJourEtatDepuisAPI() {
  String endpoint = "/api/etat?shift=" + currentShift; [cite: 39]
  String response;
  int code = appelAPI(endpoint, "GET", "", response); [cite: 40]

  if (code == 200) {
    DynamicJsonDocument doc(512); [cite: 40]
    deserializeJson(doc, response); [cite: 41]
    String statut = doc["statut"] | "Libre"; [cite: 41]
    
    if (statut == "En cours") {
      productionEnCours = true; [cite: 44]
      quantiteMax = doc["quantite_requise"] | 0; [cite: 42]
      setLED(HIGH, LOW, LOW); [cite: 46]
    } else if (statut == "En attente") {
      productionEnCours = false; [cite: 47]
      setLED(LOW, HIGH, LOW); [cite: 47]
    } else {
      productionEnCours = false; [cite: 49]
      setLED(LOW, LOW, HIGH); [cite: 49]
    }
  }
}

// ... (Gardez les fonctions incrementer/lancer/gererPedale comme dans votre code source)

void loop() {
  bool limitState = digitalRead(PIN_LIMIT_SWITCH); [cite: 97]
  bool cancelState = digitalRead(PIN_CANCEL_BUTTON); [cite: 97]

  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (lastLimitState == HIGH && limitState == LOW) {
      gererPedale(); [cite: 98]
      lastDebounceTime = millis();
    }
    if (lastCancelState == HIGH && cancelState == LOW) {
      gererAnnulation(); [cite: 99]
      lastDebounceTime = millis();
    }
  }

  lastLimitState = limitState;
  lastCancelState = cancelState; [cite: 100]

  if (millis() - lastLEDUpdate > LED_UPDATE_INTERVAL) {
    mettreAJourEtatDepuisAPI(); [cite: 105]
    lastLEDUpdate = millis();
  }
  delay(50);
}
