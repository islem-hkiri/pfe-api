#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

const char* ssid = "A17 de Hkiri";
const char* password = "4w3gshixthsz8h";

// 🔥 MAINANT C'EST L'IP DE RENDER (serveur remote)
const char* serverIP = "pfe-api-uju4.onrender.com";  // ← Serveur remote
const int serverPort = 80;  // HTTP port, pas 8000

#define LED_GREEN 26
#define LED_ORANGE 27
#define LED_RED 14
#define LIMIT_SWITCH 25
#define BTN_CANCEL   33

String shift = "B";
bool lastSwitchState = HIGH;
bool lastCancelState = HIGH;
bool webSocketConnected = false;

WebSocketsClient webSocket;
unsigned long lastHeartbeat = 0;
unsigned long lastStatusRequest = 0;

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("❌ WebSocket déconnecté!");
      webSocketConnected = false;
      break;

    case WStype_CONNECTED:
      Serial.println("✅ WebSocket connecté à Render!");
      webSocketConnected = true;
      webSocket.sendTXT("get_status");
      break;

    case WStype_TEXT:
      {
        String message = String((char*)payload);
        Serial.print("📨 Message reçu du serveur: ");
        Serial.println(message);

        if (message == "Libre") {
          Serial.println("🟢 État: LIBRE - LED VERTE");
          digitalWrite(LED_GREEN, HIGH);
          digitalWrite(LED_ORANGE, LOW);
          digitalWrite(LED_RED, LOW);
        }
        else if (message == "🟠En attente") {
          Serial.println("🟠 État: EN ATTENTE - LED ORANGE");
          digitalWrite(LED_GREEN, LOW);
          digitalWrite(LED_ORANGE, HIGH);
          digitalWrite(LED_RED, LOW);
        }
        else if (message == "🟢En cours") {
          Serial.println("🔴 État: EN COURS - LED ROUGE");
          digitalWrite(LED_GREEN, LOW);
          digitalWrite(LED_ORANGE, LOW);
          digitalWrite(LED_RED, HIGH);
        }
      }
      break;

    case WStype_ERROR:
      Serial.println("❌ Erreur WebSocket!");
      webSocketConnected = false;
      break;
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n⚠️ Démarrage ESP32...");

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_ORANGE, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(BTN_CANCEL, INPUT_PULLUP);
  
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_ORANGE, LOW);
  digitalWrite(LED_RED, LOW);

  Serial.print("🔒 Connexion au WiFi...");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n💻 WiFi connecté !");
  Serial.print("📋 IP address: ");
  Serial.println(WiFi.localIP());

  Serial.print("🔗 Connexion WebSocket à ");
  Serial.print(serverIP);
  Serial.print(":");
  Serial.println(serverPort);

  // Connexion au serveur Render (websocket)
  webSocket.begin(serverIP, serverPort, "/ws/" + shift);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
}

void loop() {
  webSocket.loop();

  if (webSocketConnected && (millis() - lastHeartbeat > 20000)) {
    webSocket.sendTXT("ping");
    lastHeartbeat = millis();
    Serial.println("💬 Heartbeat envoyé");
  }

  if (webSocketConnected && (millis() - lastStatusRequest > 3000)) {
    webSocket.sendTXT("get_status");
    lastStatusRequest = millis();
    Serial.println("🔄 Demande de statut envoyée");
  }

  bool switchState = digitalRead(LIMIT_SWITCH);
  if (lastSwitchState == HIGH && switchState == LOW && webSocketConnected) {
    Serial.println("☑️ Pédale pressée - Incrémentation");
    webSocket.sendTXT("increment");
    delay(300);
  }
  lastSwitchState = switchState;

  bool cancelState = digitalRead(BTN_CANCEL);
  if (lastCancelState == HIGH && cancelState == LOW && webSocketConnected) {
    Serial.println("🔘 Annulation pressée - Décrémentation");
    webSocket.sendTXT("decrement");
    delay(300);
  }
  lastCancelState = cancelState;

  delay(50);
}
