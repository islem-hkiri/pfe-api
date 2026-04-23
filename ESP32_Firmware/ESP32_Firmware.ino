#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ========== WiFi Configuration ==========
const char* ssid = "Infinix HOT 30";
const char* password = "chaima123";

// ========== API Local Configuration ==========
// 🔥 REMPLACE CETTE IP par l'IP de ton PC (voir étape 3)
const char* serverIP = "10.221.91.33";  // Exemple: "192.168.1.100"
const int serverPort = 8000;

// ========== Pin Configuration ==========
#define LED_GREEN 26
#define LED_ORANGE 27
#define LED_RED 14
#define LIMIT_SWITCH 32
#define BTN_CANCEL 12

// ========== Variables ==========
String shift = "B";  // ou "A" selon ta machine
bool lastSwitchState = HIGH;
bool lastCancelState = HIGH;
bool webSocketConnected = false;

WebSocketsClient webSocket;
unsigned long lastHeartbeat = 0;
unsigned long lastReconnectAttempt = 0;

// ========== Callback WebSocket ==========
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("❌ WebSocket déconnecté!");
      webSocketConnected = false;
      break;
      
    case WStype_CONNECTED:
      Serial.println("✅ WebSocket connecté!");
      webSocketConnected = true;
      // Envoyer un message de bienvenue
      webSocket.sendTXT("{\"event\":\"connected\",\"shift\":\"" + shift + "\"}");
      break;
      
    case WStype_TEXT:
      {
        String message = String((char*)payload);
        Serial.print("📨 Message reçu du serveur: ");
        Serial.println(message);
        
        // Analyser le message reçu de l'API
        DynamicJsonDocument doc(256);
        DeserializationError error = deserializeJson(doc, message);
        
        if (!error) {
          // Si c'est un message de statut
          if (doc.containsKey("statut")) {
            String statut = doc["statut"];
            Serial.print("🎯 Changement de statut reçu: ");
            Serial.println(statut);
            
            // Mettre à jour les LEDs selon le statut reçu
            digitalWrite(LED_GREEN, LOW);
            digitalWrite(LED_ORANGE, LOW);
            digitalWrite(LED_RED, LOW);
            
            if (statut == "Libre") {
              digitalWrite(LED_GREEN, HIGH);
              Serial.println("🟢 LED VERTE allumée (Libre)");
            }
            else if (statut == "🟠En attente") {
              digitalWrite(LED_ORANGE, HIGH);
              Serial.println("🟠 LED ORANGE allumée (En attente)");
            }
            else if (statut == "🟢En cours") {
              digitalWrite(LED_RED, HIGH);
              Serial.println("🔴 LED ROUGE allumée (En cours)");
            }
          }
        }
        
        // Répondre pour confirmer la réception
        webSocket.sendTXT("ACK: " + message);
      }
      break;
      
    case WStype_ERROR:
      Serial.println("❌ WebSocket erreur!");
      webSocketConnected = false;
      break;
  }
}

// ========== Setup ==========
void setup() {
  Serial.begin(115200);
  Serial.println("\n🚀 Démarrage ESP32...");
  
  // Configuration des pins
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_ORANGE, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(BTN_CANCEL, INPUT_PULLUP);
  
  // Éteindre toutes les LEDs au démarrage
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_ORANGE, LOW);
  digitalWrite(LED_RED, LOW);
  
  // Connexion WiFi
  Serial.print("📡 Connexion au WiFi");
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\n✅ WiFi connecté !");
  Serial.print("📱 IP address: ");
  Serial.println(WiFi.localIP());
  
  // Configuration WebSocket
  Serial.print("🔌 Connexion WebSocket à ");
  Serial.print(serverIP);
  Serial.print(":");
  Serial.println(serverPort);
  
  webSocket.begin(serverIP, serverPort, "/ws/" + shift);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);  // Reconnexion automatique toutes les 5s
}

// ========== Loop ==========
void loop() {
  // 1. Gérer WebSocket
  webSocket.loop();
  
  // 2. Envoyer heartbeat toutes les 30 secondes si connecté
  if (webSocketConnected && (millis() - lastHeartbeat > 30000)) {
    webSocket.sendTXT("ping");
    lastHeartbeat = millis();
    Serial.println("💓 Heartbeat envoyé");
  }
  
  // 3. Lire le capteur de pédale (LIMIT SWITCH)
  bool switchState = digitalRead(LIMIT_SWITCH);
  if (lastSwitchState == HIGH && switchState == LOW && webSocketConnected) {
    Serial.println("🦶 Pédale pressée - Incrémentation");
    
    // Envoyer l'incrément via WebSocket (ou HTTP selon ton besoin)
    // Option 1: Utiliser HTTP POST (comme avant)
    // Option 2: Envoyer via WebSocket
    webSocket.sendTXT("{\"action\":\"increment\",\"shift\":\"" + shift + "\"}");
    
    delay(300);  // Anti-rebond
  }
  lastSwitchState = switchState;
  
  // 4. Lire le bouton d'annulation
  bool cancelState = digitalRead(BTN_CANCEL);
  if (lastCancelState == HIGH && cancelState == LOW && webSocketConnected) {
    Serial.println("🔘 Bouton annulation - Décrémentation");
    webSocket.sendTXT("{\"action\":\"decrement\",\"shift\":\"" + shift + "\"}");
    delay(300);
  }
  lastCancelState = cancelState;
  
  delay(50);  // Petit délai pour ne pas surcharger
}
