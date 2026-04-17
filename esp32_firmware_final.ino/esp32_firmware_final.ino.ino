/*
 * ESP32 Firmware - VERSION FINALE (STABLE INDUSTRIEL)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

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
  }

  Serial.println("✅ WiFi connecté");
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

// ================= UPDATE FROM API =================
void mettreAJourSysteme() {

  // 🚫 ما تبدلش LED إذا production شغالة
  if (productionEnCours) return;

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + "/api/etat?shift=" + currentShift;
  https.begin(client, url);

  int code = https.GET();
  String response = https.getString();
  https.end();

  if (response.indexOf("🟠En attente") > 0) {
    setLED(LOW, HIGH, LOW);
  }
  else {
    setLED(LOW, LOW, HIGH);
  }
}

// ================= PEDALE =================
void gererPedale() {

  // 🔴 أول نزلة = START
  if (!productionEnCours) {

    Serial.println("🚀 START");

    // 🔥 LED rouge مباشرة
    setLED(HIGH, LOW, LOW);

    productionEnCours = true;

    // API
    postRequest("/api/lancer_automatique");
  }

  // 🟢 بقية النزلات = +1
  else {

    Serial.println("➕ INCREMENT");

    String res = postRequest("/api/increment");

    if (res.indexOf("\"termine\":true") > 0) {

      Serial.println("🏁 FIN");

      productionEnCours = false;

      // blink vert
      for (int i = 0; i < 3; i++) {
        setLED(LOW, LOW, HIGH);
        delay(150);
        setLED(LOW, LOW, LOW);
        delay(150);
      }
    }
  }
}

// ================= CANCEL =================
void gererAnnulation() {
  if (productionEnCours) {
    Serial.println("➖ DECREMENT");
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
