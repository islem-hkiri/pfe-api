#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>

const char* ssid = "BEE HUAWEI-1CB0";
const char* password = "485754439C621CB0";
const char* serverIP = "pfe-api-uju4.onrender.com";

#define LED_GREEN 26
#define LED_ORANGE 27
#define LED_RED 14
#define LIMIT_SWITCH 25
#define BTN_CANCEL 33

String shift = "B";
bool lastSwitchState = HIGH;
bool lastCancelState = HIGH;
bool webSocketConnected = false;
unsigned long lastHeartbeat = 0;
unsigned long lastStatusRequest = 0;
unsigned long lastShiftCheck = 0;

WebSocketsClient webSocket;

// ═══════════════════════════════
// LEDS
// ═══════════════════════════════
void setLED(String etat) {
  if (etat == "Libre") {
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_ORANGE, LOW);
    digitalWrite(LED_RED, LOW);
    Serial.println("🟢 LED: VERTE (Libre)");
  }
  else if (etat.indexOf("attente") != -1 || etat.indexOf("En attente") != -1) {
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_ORANGE, HIGH);
    digitalWrite(LED_RED, LOW);
    Serial.println("🟠 LED: ORANGE (En attente)");
  }
  else if (etat.indexOf("cours") != -1 || etat.indexOf("En cours") != -1) {
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_ORANGE, LOW);
    digitalWrite(LED_RED, HIGH);
    Serial.println("🔴 LED: ROUGE (En cours)");
  }
  else {
    Serial.print("⚠️ État inconnu: ");
    Serial.println(etat);
  }
}

void flashAllLEDs() {
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_ORANGE, HIGH);
  digitalWrite(LED_RED, HIGH);
  delay(300);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_ORANGE, LOW);
  digitalWrite(LED_RED, LOW);
  delay(200);
}

// ═══════════════════════════════
// WEBSOCKET
// ═══════════════════════════════
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("❌ WebSocket déconnecté!");
      webSocketConnected = false;
      break;

    case WStype_CONNECTED:
      Serial.println("✅ WebSocket connecté!");
      webSocketConnected = true;
      delay(200);
      webSocket.sendTXT("get_status");
      break;

    case WStype_TEXT: {
      String message = String((char*)payload);
      Serial.print("📨 Reçu: ");
      Serial.println(message);
      if (message != "pong") {
        setLED(message);
      }
      break;
    }

    case WStype_ERROR:
      Serial.println("❌ Erreur WebSocket!");
      webSocketConnected = false;
      break;
  }
}

// ═══════════════════════════════
// GET ACTIVE SHIFT (HTTP)
// ═══════════════════════════════
String getActiveShift() {
  HTTPClient http;
  http.begin("https://pfe-api-uju4.onrender.com/api/get_active_shift");
  http.setTimeout(5000);
  int code = http.GET();
  if (code == 200) {
    String payload = http.getString();
    int idx = payload.indexOf("\"shift\":\"");
    if (idx != -1) {
      String s = payload.substring(idx + 9, idx + 10);
      http.end();
      return s;
    }
  }
  http.end();
  return shift;
}

// ═══════════════════════════════
// RECONNECT SHIFT
// ═══════════════════════════════
void connectToShift(String s) {
  Serial.print("🔗 Connexion WebSocket shift: ");
  Serial.println(s);
  webSocket.disconnect();
  delay(500);
  webSocket.beginSSL(serverIP, 443, ("/ws/" + s).c_str());
}

// ═══════════════════════════════
// SETUP
// ═══════════════════════════════
void setup() {
  Serial.begin(115200);

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_ORANGE, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(BTN_CANCEL, INPUT_PULLUP);

  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_ORANGE, LOW);
  digitalWrite(LED_RED, LOW);

  Serial.print("🔒 Connexion WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi connecté!");

  connectToShift(shift);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
}

// ═══════════════════════════════
// LOOP
// ═══════════════════════════════
void loop() {
  webSocket.loop();

  // Heartbeat kol 20s
  if (webSocketConnected && millis() - lastHeartbeat > 20000) {
    webSocket.sendTXT("ping");
    lastHeartbeat = millis();
  }

  // Get status kol 3s
  if (webSocketConnected && millis() - lastStatusRequest > 3000) {
    webSocket.sendTXT("get_status");
    lastStatusRequest = millis();
  }

  // Pédale — increment
  bool switchState = digitalRead(LIMIT_SWITCH);
  if (lastSwitchState == HIGH && switchState == LOW && webSocketConnected) {
    Serial.println("☑️ Pédale — increment");
    webSocket.sendTXT("increment");
    delay(300);
  }
  lastSwitchState = switchState;

  // Bouton annuler — decrement
  bool cancelState = digitalRead(BTN_CANCEL);
  if (lastCancelState == HIGH && cancelState == LOW && webSocketConnected) {
    Serial.println("🔘 Annuler — decrement");
    webSocket.sendTXT("decrement");
    delay(300);
  }
  lastCancelState = cancelState;

  // Vérifier shift kol 5s
  if (millis() - lastShiftCheck > 5000) {
    lastShiftCheck = millis();
    String newShift = getActiveShift();
    if (newShift != shift) {
      Serial.print("🔄 Shift changé: ");
      Serial.print(shift);
      Serial.print(" → ");
      Serial.println(newShift);
      shift = newShift;
      flashAllLEDs();
      connectToShift(shift);
    }
  }

  delay(50);
}
