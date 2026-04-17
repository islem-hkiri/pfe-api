/*
 * ESP32 Firmware - Poste Soudure Ultrasons
 * Logic: 
 * - Green LED: No tasks.
 * - Orange LED: Task waiting (First pedal press -> Launch).
 * - Red LED: Task in progress (Pedal press -> Increment).
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

// ==================== WiFi Configuration ====================
const char* ssid = "BEE HUAWEI-1CB0";
const char* password = "485754439C621CB0";

// ==================== API sur Render (HTTPS) ====================
const char* serverHost = "pfe-api-vure.onrender.com";

// ==================== Broches ====================
const int PIN_LIMIT_SWITCH = 13;   // Pédale
const int PIN_CANCEL_BUTTON = 12;  // Bouton annulation
const int PIN_LED_ROUGE = 14;      // Production en cours
const int PIN_LED_ORANGE = 27;     // File d'attente non vide
const int PIN_LED_VERTE = 26;      // Machine disponible

// ==================== Variables globales ====================
String currentShift = "B";   
String currentStatus = "Libre"; 

unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 150;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 2000; 

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
  Serial.println("\n✅ WiFi connected!");
}

String makeHTTPRequest(String method, String endpoint, String body) {
  if (WiFi.status() != WL_CONNECTED) return "";
  WiFiClientSecure client;
  client.setInsecure(); 
  HTTPClient https;
  String url = "https://" + String(serverHost) + endpoint;
  https.begin(client, url);
  https.addHeader("Content-Type", "application/json");
  int httpCode = (method == "GET") ? https.GET() : https.POST(body);
  String response = (httpCode > 0) ? https.getString() : "";
  https.end();
  return response;
}

void gererPedale() {
  String body = "{\"shift\":\"" + currentShift + "\"}";
  
  if (currentStatus == "🟠En attente") {
    Serial.println("🚀 First press: Launching production...");
    String response = makeHTTPRequest("POST", "/api/lancer_automatique", body);
    if (response.indexOf("\"success\":true") > 0) {
      Serial.println("✅ Production started!");
    }
  } 
  else if (currentStatus == "🟢En cours") {
    Serial.println("➕ Incrementing counter...");
    String response = makeHTTPRequest("POST", "/api/increment", body);
    if (response.indexOf("\"termine\":true") > 0) {
      Serial.println("🏁 Quantity reached! Task finished.");
    }
  }
}

void gererAnnulation() {
  if (currentStatus == "🟢En cours") {
    Serial.println("➖ Decrementing (-1)...");
    String body = "{\"shift\":\"" + currentShift + "\"}";
    makeHTTPRequest("POST", "/api/decrement", body);
  }
}

void mettreAJourSysteme() {
  String endpoint = "/api/etat?shift=" + currentShift;
  String response = makeHTTPRequest("GET", endpoint, "");
  if (response.length() == 0) return;

  if (response.indexOf("\"statut\":\"🟢En cours\"") > 0) {
    currentStatus = "🟢En cours";
    digitalWrite(PIN_LED_ROUGE, HIGH);
    digitalWrite(PIN_LED_ORANGE, LOW);
    digitalWrite(PIN_LED_VERTE, LOW);
  } 
  else if (response.indexOf("\"statut\":\"🟠En attente\"") > 0) {
    currentStatus = "🟠En attente";
    digitalWrite(PIN_LED_ROUGE, LOW);
    digitalWrite(PIN_LED_ORANGE, HIGH);
    digitalWrite(PIN_LED_VERTE, LOW);
  } 
  else {
    currentStatus = "Libre";
    digitalWrite(PIN_LED_ROUGE, LOW);
    digitalWrite(PIN_LED_ORANGE, LOW);
    digitalWrite(PIN_LED_VERTE, HIGH);
  }
}

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
  delay(20);
}
