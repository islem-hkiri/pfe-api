
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// WIFI
const char* ssid = "Infinix HOT 30";
const char* password = "chaima123";

// API
String server = "https://pfe-api-uju4.onrender.com";

// PINS
#define LED_GREEN 26
#define LED_ORANGE 27
#define LED_RED 14

#define LIMIT_SWITCH 32
#define BTN_CANCEL 12

// VARIABLES
String shift = "A";
bool lastSwitchState = HIGH;
bool lastCancelState = HIGH;

void setup() {
  Serial.begin(115200);

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_ORANGE, OUTPUT);
  pinMode(LED_RED, OUTPUT);

  pinMode(LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(BTN_CANCEL, INPUT_PULLUP);

  WiFi.begin(ssid, password);

  Serial.print("Connexion WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connecté !");
}

void loop() {

  if (WiFi.status() == WL_CONNECTED) {

    // 🔹 1. GET ETAT
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.begin(client, server + "/api/etat?shift=" + shift);

    int code = http.GET();

    if (code > 0) {
      String payload = http.getString();
      Serial.println("Response:");
      Serial.println(payload);

      DynamicJsonDocument doc(512);
      deserializeJson(doc, payload);

      String statut = doc["statut"];

      // RESET LED
      digitalWrite(LED_GREEN, LOW);
      digitalWrite(LED_ORANGE, LOW);
      digitalWrite(LED_RED, LOW);

      if (statut == "Libre") {
        digitalWrite(LED_GREEN, HIGH);
      }
      else if (statut == "En attente") {
        digitalWrite(LED_ORANGE, HIGH);
      }
      else if (statut == "En cours") {
        digitalWrite(LED_RED, HIGH);
      }

    } else {
      Serial.print("Erreur GET: ");
      Serial.println(code);
    }

    http.end();

    // 🔹 2. LIMIT SWITCH (INCREMENT)
    bool switchState = digitalRead(LIMIT_SWITCH);

    if (lastSwitchState == HIGH && switchState == LOW) {
      Serial.println("Pedale pressée");

      WiFiClientSecure client2;
      client2.setInsecure();

      HTTPClient http2;
      http2.begin(client2, server + "/api/increment");
      http2.addHeader("Content-Type", "application/json");

      String body = "{\"shift\":\"" + shift + "\"}";
      int code2 = http2.POST(body);

      Serial.print("Increment: ");
      Serial.println(code2);

      http2.end();
      delay(300);
    }

    lastSwitchState = switchState;

    // 🔹 3. BOUTON CANCEL (DECREMENT)
    bool cancelState = digitalRead(BTN_CANCEL);

    if (lastCancelState == HIGH && cancelState == LOW) {
      Serial.println("Annulation -1");

      WiFiClientSecure client3;
      client3.setInsecure();

      HTTPClient http3;
      http3.begin(client3, server + "/api/decrement");
      http3.addHeader("Content-Type", "application/json");

      String body = "{\"shift\":\"" + shift + "\"}";
      http3.POST(body);

      http3.end();
      delay(300);
    }

    lastCancelState = cancelState;
  }

  delay(200);
}
