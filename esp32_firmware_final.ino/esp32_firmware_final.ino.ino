/*
 * ESP32 Firmware - VERSION FINALE (STABLE INDUSTRIEL) - CORRIGEE
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

// ================= WIFI =================
const char* ssid = "BEE HUAWEI-1CB0";
const char* password = "485754439C621CB0";

// ================= API =================
const char* serverHost = "pfe-api-vure.onrender.com";

// ================= PINS =================
const int PIN_LIMIT_SWITCH = 13;
const int PIN_CANCEL_BUTTON = 12;
const int PIN_LED_ROUGE = 14;
const int PIN_LED_ORANGE = 27;
const int PIN_LED_VERTE = 26;

// ================= VARIABLES =================
String currentShift = "B";
bool productionEnCours = false;

unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 100;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 2000;

// ================= SETUP =================
void setup() {
  Serial.begin(115200);

  pinMode(PIN_LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(PIN_CANCEL_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_VERTE, OUTPUT);

  digitalWrite(PIN_LED_ROUGE, LOW);
  digitalWrite(PIN_LED_ORANGE, LOW);
  digitalWrite(PIN_LED_VERTE, LOW);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connecte");

  delay(1000);
  synchroniserEtatProduction();
}

// ================= HTTP =================
String postRequest(String endpoint) {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + endpoint;
  https.begin(client, url);
  https.addHeader("Content-Type", "application/json");

  int code = https.POST("{\"shift\":\"" + currentShift + "\"}");
  String res = https.getString();

  https.end();
  return res;
}

// ================= LED CONTROL =================
void setLED(bool r, bool o, bool v) {
  digitalWrite(PIN_LED_ROUGE, r);
  digitalWrite(PIN_LED_ORANGE, o);
  digitalWrite(PIN_LED_VERTE, v);
}

// ================= SYNCHRONISATION DEMARRAGE =================
void synchroniserEtatProduction() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + "/api/etat?shift=" + currentShift;
  https.begin(client, url);
  int code = https.GET();
  if (code == 200) {
    String response = https.getString();
    DynamicJsonDocument doc(1024);
    deserializeJson(doc, response);
    String statut = doc["statut"] | "";
    
    if (statut.indexOf("En cours") >= 0) {
      productionEnCours = true;
      setLED(HIGH, LOW, LOW);
      Serial.println("Production deja en cours (recupere depuis API)");
    } else {
      productionEnCours = false;
      if (statut.indexOf("En attente") >= 0) {
        setLED(LOW, HIGH, LOW);
      } else {
        setLED(LOW, LOW, HIGH);
      }
    }
  } else {
    Serial.println("Impossible de synchroniser l'etat au demarrage");
  }
  https.end();
}

// ================= UPDATE FROM API (LEDS) =================
void mettreAJourSysteme() {
  if (productionEnCours) return;

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + "/api/etat?shift=" + currentShift;
  https.begin(client, url);
  int code = https.GET();
  if (code == 200) {
    String response = https.getString();
    DynamicJsonDocument doc(1024);
    deserializeJson(doc, response);
    String statut = doc["statut"] | "";

    if (statut.indexOf("En attente") >= 0) {
      setLED(LOW, HIGH, LOW);
    } else if (statut.indexOf("En cours") >= 0) {
      productionEnCours = true;
      setLED(HIGH, LOW, LOW);
    } else {
      setLED(LOW, LOW, HIGH);
    }
  }
  https.end();
}

// ================= PEDALE =================
void gererPedale() {
  if (!productionEnCours) {
    Serial.println("START");
    setLED(HIGH, LOW, LOW);
    productionEnCours = true;
    postRequest("/api/lancer_automatique");
  } else {
    Serial.println("INCREMENT");
    String res = postRequest("/api/increment");
    
    DynamicJsonDocument doc(256);
    deserializeJson(doc, res);
    bool termine = doc["termine"] | false;
    
    if (termine) {
      Serial.println("FIN");
      productionEnCours = false;
      for (int i = 0; i < 3; i++) {
        setLED(LOW, LOW, HIGH);
        delay(150);
        setLED(LOW, LOW, LOW);
        delay(150);
      }
      mettreAJourSysteme();
    }
  }
}

// ================= CANCEL =================
void gererAnnulation() {
  if (productionEnCours) {
    Serial.println("DECREMENT");
    postRequest("/api/decrement");
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
    mettreAJourSysteme();
    lastLEDUpdate = millis();
  }

  delay(50);
}
