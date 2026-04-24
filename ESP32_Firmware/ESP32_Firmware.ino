#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

const char* ssid = "Infinix HOT 30";
const char* password = "chaima123";

// 🔥 CHANGE CETTE IP (celle de ton PC)
const char* serverIP = "10.221.91.33";
const int serverPort = 8000;

#define LED_GREEN 26
#define LED_ORANGE 27
#define LED_RED 14
#define BTN_INCR 32      // Bouton incrémentation (pédale)
#define BTN_DECR 12      // Bouton décrémentation (annulation)

String shift = "B";  // Change A ou B selon ton shift

bool webSocketConnected = false;
unsigned long lastHeartbeat = 0;
unsigned long lastStatusRequest = 0;

// Variables pour anti-rebond
bool lastIncrState = HIGH;
bool lastDecrState = HIGH;
unsigned long lastButtonTime = 0;

WebSocketsClient webSocket;

// ========== GESTION DES LEDS ==========
void setLEDs(String status) {
  if (status == "Libre") {
    Serial.println("🟢 STATUT: LIBRE - LED VERTE");
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_ORANGE, LOW);
    digitalWrite(LED_RED, LOW);
  }
  else if (status == "🟠En attente") {
    Serial.println("🟠 STATUT: EN ATTENTE - LED ORANGE");
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_ORANGE, HIGH);
    digitalWrite(LED_RED, LOW);
  }
  else if (status == "🟢En cours") {
    Serial.println("🔴 STATUT: EN COURS - LED ROUGE");
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_ORANGE, LOW);
    digitalWrite(LED_RED, HIGH);
  }
  else {
    // Si message inconnu, on garde vert par défaut
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_ORANGE, LOW);
    digitalWrite(LED_RED, LOW);
  }
}

// ========== DEMANDER LE STATUT AU SERVEUR ==========
void requestStatus() {
  if (webSocketConnected) {
    webSocket.sendTXT("get_status");
    Serial.println("📡 Demande de statut envoyée");
  }
}

// ========== WEBSOCKET EVENTS ==========
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("❌ WebSocket déconnecté!");
      webSocketConnected = false;
      // LEDs clignotent pour indiquer déconnexion
      digitalWrite(LED_GREEN, LOW);
      digitalWrite(LED_ORANGE, LOW);
      digitalWrite(LED_RED, HIGH);
      delay(200);
      digitalWrite(LED_RED, LOW);
      break;

    case WStype_CONNECTED:
      Serial.println("✅ WebSocket connecté!");
      webSocketConnected = true;
      // Demander le statut immédiatement après connexion
      delay(500);
      requestStatus();
      break;

    case WStype_TEXT:
      {
        String message = String((char*)payload);
        Serial.print("📨 Message reçu: ");
        Serial.println(message);
        
        // Si c'est un statut, mettre à jour les LEDs
        if (message == "Libre" || message == "🟠En attente" || message == "🟢En cours") {
          setLEDs(message);
        }
        else if (message == "pong") {
          // Heartbeat reçu, rien à faire
          Serial.println("💓 Pong reçu");
        }
        else if (message == "ack_incr") {
          Serial.println("✅ Incrémentation confirmée par le serveur");
        }
        else if (message == "ack_decr") {
          Serial.println("✅ Décrémentation confirmée par le serveur");
        }
        else {
          Serial.print("📝 Autre message: ");
          Serial.println(message);
        }
      }
      break;

    case WStype_ERROR:
      Serial.println("❌ Erreur WebSocket!");
      webSocketConnected = false;
      break;
  }
}

// ========== SETUP ==========
void setup() {
  Serial.begin(115200);
  Serial.println("\n⚠️ Démarrage ESP32 - Système Production");
  
  // Initialiser LEDs
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_ORANGE, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(BTN_INCR, INPUT_PULLUP);
  pinMode(BTN_DECR, INPUT_PULLUP);
  
  // Éteindre toutes les LEDs
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_ORANGE, LOW);
  digitalWrite(LED_RED, LOW);
  
  // LED rouge clignote pendant la connexion
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_RED, HIGH);
    delay(200);
    digitalWrite(LED_RED, LOW);
    delay(200);
  }
  
  // Connexion WiFi
  Serial.print("🔒 Connexion au WiFi...");
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n💻 WiFi connecté !");
    Serial.print("📋 IP address: ");
    Serial.println(WiFi.localIP());
    
    // WebSocket connection
    webSocket.begin(serverIP, serverPort, "/ws/" + shift);
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
  } else {
    Serial.println("\n❌ WiFi non connecté! Vérifie les identifiants");
  }
  
  // Initialiser lastStatusRequest
  lastStatusRequest = millis();
}

// ========== LOOP ==========
void loop() {
  webSocket.loop();
  
  // Heartbeat toutes les 20 secondes
  if (webSocketConnected && (millis() - lastHeartbeat > 20000)) {
    webSocket.sendTXT("ping");
    lastHeartbeat = millis();
    Serial.println("💬 Heartbeat envoyé");
  }
  
  // Demander le statut toutes les 10 secondes
  if (webSocketConnected && (millis() - lastStatusRequest > 10000)) {
    requestStatus();
    lastStatusRequest = millis();
  }
  
  // ========== BOUTON INCRÉMENTATION (Pédale) ==========
  bool incrState = digitalRead(BTN_INCR);
  if (lastIncrState == HIGH && incrState == LOW && webSocketConnected) {
    unsigned long now = millis();
    if (now - lastButtonTime > 200) {  // Anti-rebond
      Serial.println("☑️ Pédale pressée - Incrémentation");
      webSocket.sendTXT("increment");
      lastButtonTime = now;
      
      // Feedback visuel: LED clignote vert rapidement
      digitalWrite(LED_GREEN, HIGH);
      delay(50);
      if (digitalRead(LED_RED) == LOW) {
        digitalWrite(LED_GREEN, LOW);
      }
    }
  }
  lastIncrState = incrState;
  
  // ========== BOUTON DÉCRÉMENTATION (Annulation) ==========
  bool decrState = digitalRead(BTN_DECR);
  if (lastDecrState == HIGH && decrState == LOW && webSocketConnected) {
    unsigned long now = millis();
    if (now - lastButtonTime > 200) {
      Serial.println("🔘 Bouton Annulation - Décrémentation");
      webSocket.sendTXT("decrement");
      lastButtonTime = now;
      
      // Feedback visuel: LED orange clignote
      digitalWrite(LED_ORANGE, HIGH);
      delay(50);
      if (digitalRead(LED_RED) == LOW && digitalRead(LED_GREEN) == LOW) {
        digitalWrite(LED_ORANGE, LOW);
      }
    }
  }
  lastDecrState = decrState;
  
  delay(10);
}
