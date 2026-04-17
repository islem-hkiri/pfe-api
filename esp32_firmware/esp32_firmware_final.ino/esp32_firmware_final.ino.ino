/*
 * ESP32 Firmware - Poste Soudure Ultrasons
 * =========================================
 * Fonctionnalités :
 * - Lecture d'un limit switch (pédale) pour incrémenter le compteur
 * - Lecture d'un bouton d'annulation pour décrémenter
 * - Contrôle de 3 LEDs (Vert, Orange, Rouge)
 * - Découverte automatique du serveur via UDP broadcast
 * - Communication HTTP avec l'API FastAPI
 */
/*
 * ESP32 Firmware - Poste Soudure Ultrasons
 * Version complète avec HTTP requests et LEDs
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

// ==================== WiFi Configuration ====================
const char* ssid = "BEE HUAWEI-1CB0";        // ⚠️ Modifier si besoin
const char* password = "485754439C621CB0";   // ⚠️ Modifier si besoin

// ==================== API en ligne sur Render ====================
// ⚠️ REMPLACE PAR TON URL RENDER !
const char* serverHost = "https://pfe-api-erbl.onrender.com";  // ← METS TON URL ICI
const int SERVER_PORT = 443;  // HTTPS

// ==================== Pins ====================
const int PIN_LIMIT_SWITCH = 13;
const int PIN_CANCEL_BUTTON = 12;
const int PIN_LED_ROUGE = 14;
const int PIN_LED_ORANGE = 27;
const int PIN_LED_VERTE = 26;

// ==================== Variables ====================
String currentShift = "A";
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;
unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 2000;  // Mise à jour toutes les 2 secondes

// ==================== Setup ====================
void setup() {
  Serial.begin(115200);
  Serial.println("\n\n╔════════════════════════════════════════╗");
  Serial.println("║   ESP32 - Poste Soudure Ultrasons     ║");
  Serial.println("║         Mode EN LIGNE (Render)        ║");
  Serial.println("╚════════════════════════════════════════╝\n");
  
  pinMode(PIN_LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(PIN_CANCEL_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_VERTE, OUTPUT);
  
  digitalWrite(PIN_LED_ROUGE, LOW);
  digitalWrite(PIN_LED_ORANGE, LOW);
  digitalWrite(PIN_LED_VERTE, LOW);
  
  // Connexion WiFi
  Serial.print("📡 Connexion au WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi connecté !");
    Serial.print("📡 IP locale: ");
    Serial.println(WiFi.localIP());
    digitalWrite(PIN_LED_VERTE, HIGH);
    delay(500);
    digitalWrite(PIN_LED_VERTE, LOW);
  } else {
    Serial.println("\n❌ Échec de connexion WiFi");
  }
  
  Serial.print("🌐 API Server: ");
  Serial.println(serverHost);
}

// ==================== Appel HTTPS ====================
String makeHTTPRequest(String method, String endpoint, String body) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi déconnecté");
    return "";
  }
  
  WiFiClientSecure client;
  client.setInsecure();  // Désactive la vérification SSL (pour test)
  
  HTTPClient https;
  String url = "https://" + String(serverHost) + endpoint;
  
  Serial.print("📤 Requête: ");
  Serial.println(method + " " + url);
  
  https.begin(client, url);
  https.addHeader("Content-Type", "application/json");
  
  int httpCode;
  if (method == "GET") {
    httpCode = https.GET();
  } else {
    httpCode = https.POST(body);
  }
  
  String response = "";
  if (httpCode > 0) {
    response = https.getString();
    Serial.print("📥 Réponse (" + String(httpCode) + "): ");
    Serial.println(response);
  } else {
    Serial.print("❌ Erreur HTTP: ");
    Serial.println(httpCode);
  }
  
  https.end();
  return response;
}

// ==================== Incrémentation ====================
void incrementerProduction() {
  Serial.println("\n🔘 [ACTION] Pédale appuyée - Incrémentation");
  String body = "{\"shift\":\"" + currentShift + "\"}";
  String response = makeHTTPRequest("POST", "/api/increment", body);
  
  if (response.indexOf("\"termine\":true") > 0) {
    Serial.println("🎉 Production terminée !");
    // Clignotement LED verte
    for (int i = 0; i < 3; i++) {
      digitalWrite(PIN_LED_VERTE, HIGH);
      delay(200);
      digitalWrite(PIN_LED_VERTE, LOW);
      delay(200);
    }
  }
}

// ==================== Décrémentation ====================
void decrementerProduction() {
  Serial.println("\n🔘 [ACTION] Annulation appuyée - Décrémentation");
  String body = "{\"shift\":\"" + currentShift + "\"}";
  makeHTTPRequest("POST", "/api/decrement", body);
}

// ==================== Mise à jour des LEDs ====================
void mettreAJourLEDs() {
  String endpoint = "/api/etat?shift=" + currentShift;
  String response = makeHTTPRequest("GET", endpoint, "");
  
  if (response.length() > 0) {
    if (response.indexOf("\"machine_disponible\":true") > 0) {
      digitalWrite(PIN_LED_VERTE, HIGH);
      digitalWrite(PIN_LED_ROUGE, LOW);
      
      if (response.indexOf("\"demande_id\":null") == -1 && 
          response.indexOf("\"demande_id\":0") == -1) {
        digitalWrite(PIN_LED_ORANGE, HIGH);
      } else {
        digitalWrite(PIN_LED_ORANGE, LOW);
      }
    } else {
      digitalWrite(PIN_LED_VERTE, LOW);
      digitalWrite(PIN_LED_ROUGE, HIGH);
      digitalWrite(PIN_LED_ORANGE, LOW);
    }
  } else {
    // Erreur de communication - LED rouge clignotante
    digitalWrite(PIN_LED_VERTE, LOW);
    digitalWrite(PIN_LED_ORANGE, LOW);
    digitalWrite(PIN_LED_ROUGE, HIGH);
  }
}

// ==================== Loop Principal ====================
void loop() {
  bool limitState = digitalRead(PIN_LIMIT_SWITCH);
  bool cancelState = digitalRead(PIN_CANCEL_BUTTON);
  
  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (lastLimitState == HIGH && limitState == LOW) {
      incrementerProduction();
    }
    
    if (lastCancelState == HIGH && cancelState == LOW) {
      decrementerProduction();
    }
    
    lastDebounceTime = millis();
  }
  
  lastLimitState = limitState;
  lastCancelState = cancelState;
  
  // Mise à jour périodique des LEDs
  if (millis() - lastLEDUpdate > LED_UPDATE_INTERVAL) {
    mettreAJourLEDs();
    lastLEDUpdate = millis();
  }
  
  delay(50);
}
