#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h>

// ================= WIFI =================
const char* ssid = "Infinix HOT 30";
const char* password = "chaima123";

// ================= SERVER =================
const char* serverHost = "pfe-api-uju4.onrender.com";
const int serverPort = 443;

// ================= PINS =================
const int PIN_LIMIT_SWITCH = 32;
const int PIN_CANCEL_BUTTON = 12;
const int PIN_LED_ROUGE = 14;
const int PIN_LED_ORANGE = 27;
const int PIN_LED_VERTE = 26;

// ================= VARIABLES =================
String currentShift = "B";
bool productionEnCours = false;
int compteurLocal = 0;
int quantiteMax = 0;
int demandeId = 0;

unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 100;

bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 10000;

// ================= SETUP =================
void setup() {
  Serial.begin(115200);

  pinMode(PIN_LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(PIN_CANCEL_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_VERTE, OUTPUT);

  setLED(LOW, LOW, LOW);

  WiFi.begin(ssid, password);
  Serial.print("Connexion WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connecté !");
  mettreAJourEtatDepuisAPI();
}

// ================= LED =================
void setLED(bool rouge, bool orange, bool verte) {
  digitalWrite(PIN_LED_ROUGE, rouge);
  digitalWrite(PIN_LED_ORANGE, orange);
  digitalWrite(PIN_LED_VERTE, verte);
}

// ================= API HTTPS =================
int appelAPI(String endpoint, String method, String body, String &response) {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    return -1;
  }

  WiFiClientSecure *client = new WiFiClientSecure;

  if (!client) return -1;

  client->setInsecure(); // ignore SSL

  HTTPClient http;
  String url = "https://" + String(serverHost) + endpoint;

  http.begin(*client, url);
  http.addHeader("Content-Type", "application/json");

  int httpCode;

  if (method == "GET") {
    httpCode = http.GET();
  } else {
    httpCode = http.POST(body);
  }

  if (httpCode > 0) {
    response = http.getString();
  } else {
    Serial.println("Erreur HTTP");
  }

  http.end();
  delete client;

  return httpCode;
}

// ================= GET ETAT =================
void mettreAJourEtatDepuisAPI() {
  String response;
  int code = appelAPI("/api/etat?shift=" + currentShift, "GET", "", response);

  if (code == 200) {
    DynamicJsonDocument doc(512);
    deserializeJson(doc, response);

    String statut = doc["statut"] | "Libre";

    if (statut == "En cours") {
      productionEnCours = true;
      quantiteMax = doc["quantite_requise"] | 0;
      demandeId = doc["id"] | 0;
      setLED(HIGH, LOW, LOW);
    }
    else if (statut == "En attente") {
      productionEnCours = false;
      setLED(LOW, HIGH, LOW);
    }
    else {
      productionEnCours = false;
      setLED(LOW, LOW, HIGH);
    }
  }
}

// ================= START =================
void lancerProduction() {
  String response;
  int code = appelAPI("/api/start", "POST", "{}", response);

  if (code == 200) {
    Serial.println("Production lancée");
    productionEnCours = true;
    compteurLocal = 0;
  }
}

// ================= INCREMENT =================
void incrementerProduction() {
  DynamicJsonDocument doc(256);
  doc["id"] = demandeId;
  doc["quantite"] = compteurLocal + 1;

  String body;
  serializeJson(doc, body);

  String response;
  int code = appelAPI("/api/increment", "POST", body, response);

  if (code == 200) {
    compteurLocal++;
    Serial.println("Increment OK");
  }
}

// ================= CANCEL =================
void gererAnnulation() {
  String response;
  int code = appelAPI("/api/cancel", "POST", "{}", response);

  if (code == 200) {
    Serial.println("Production annulée");
    productionEnCours = false;
    compteurLocal = 0;
    setLED(LOW, LOW, HIGH);
  }
}

// ================= PEDALE =================
void gererPedale() {
  if (!productionEnCours) {
    lancerProduction();
  } else {
    if (compteurLocal < quantiteMax) {
      incrementerProduction();
    } else {
      Serial.println("Quantité atteinte");
    }
  }
}

// ================= LOOP =================
void loop() {
  bool limitState = digitalRead(PIN_LIMIT_SWITCH);
  bool cancelState = digitalRead(PIN_CANCEL_BUTTON);

  if ((millis() - lastDebounceTime) > debounceDelay) {

    if (lastLimitState == HIGH && limitState == LOW) {
      gererPedale();
      lastDebounceTime = millis();
    }

    if (lastCancelState == HIGH && cancelState == LOW) {
      gererAnnulation();
      lastDebounceTime = millis();
    }
  }

  lastLimitState = limitState;
  lastCancelState = cancelState;

  if (millis() - lastLEDUpdate > LED_UPDATE_INTERVAL) {
    mettreAJourEtatDepuisAPI();
    lastLEDUpdate = millis();
  }

  delay(50);
}
