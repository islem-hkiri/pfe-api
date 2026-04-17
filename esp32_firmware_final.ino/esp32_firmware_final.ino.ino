/*
 * ESP32 Firmware - Poste Soudure Ultrasons (Version Optimisée)
 * - LED Verte: Machine disponible + aucune tâche en attente
 * - LED Orange: Une tâche est en attente
 * - LED Rouge: Production en cours (s’allume immédiatement après 1er appui pédale)
 * - Pédale : 1er appui = lancer production ; suivants = incrémenter
 * - Bouton Annuler : décrémente
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

// ==================== WiFi Configuration ====================
const char* ssid = "BEE HUAWEI-1CB0";
const char* password = "485754439C621CB0";

// ==================== API sur Render (HTTPS) ====================
const char* serverHost = "pfe-api-vure.onrender.com";
const int SERVER_PORT = 443;

// ==================== Broches ====================
const int PIN_LIMIT_SWITCH = 13;   // Pédale
const int PIN_CANCEL_BUTTON = 12;  // Bouton annulation
const int PIN_LED_ROUGE = 14;      // Production en cours
const int PIN_LED_ORANGE = 27;     // File d'attente non vide
const int PIN_LED_VERTE = 26;      // Machine disponible

// ==================== Variables globales ====================
String currentShift = "B";   // Changez en "A" si nécessaire
bool productionEnCours = false;

unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 100;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 2000;

// ==================== Setup ====================
void setup() {
  Serial.begin(115200);
  Serial.println("\n✅ ESP32 - Poste Soudure Ultrasons (Mode Render)");

  pinMode(PIN_LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(PIN_CANCEL_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_VERTE, OUTPUT);

  digitalWrite(PIN_LED_ROUGE, LOW);
  digitalWrite(PIN_LED_ORANGE, LOW);
  digitalWrite(PIN_LED_VERTE, LOW);

  Serial.print("📡 Connexion WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi connecté !");
  Serial.print("📡 IP locale : ");
  Serial.println(WiFi.localIP());
}

// ==================== Fonction générique pour appels HTTPS ====================
String makeHTTPRequest(String method, String endpoint, String body) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi déconnecté");
    return "";
  }

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + endpoint;
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
    Serial.println("📥 Réponse (" + String(httpCode) + "): " + response);
  } else {
    Serial.println("❌ Erreur HTTP: " + String(httpCode));
  }

  https.end();
  return response;
}

// ==================== Mise à jour état + LEDs ====================
void mettreAJourSysteme() {
  String endpoint = "/api/etat?shift=" + currentShift;
  String response = makeHTTPRequest("GET", endpoint, "");

  if (response.length() == 0) {
    digitalWrite(PIN_LED_ROUGE, HIGH);
    digitalWrite(PIN_LED_ORANGE, LOW);
    digitalWrite(PIN_LED_VERTE, LOW);
    return;
  }

  bool enCours = (response.indexOf("\"statut\":\"🟢En cours\"") > 0);
  bool enAttente = (response.indexOf("\"statut\":\"🟠En attente\"") > 0);

  productionEnCours = enCours;

  if (enCours) {
    digitalWrite(PIN_LED_ROUGE, HIGH);
    digitalWrite(PIN_LED_ORANGE, LOW);
    digitalWrite(PIN_LED_VERTE, LOW);
  }
  else if (enAttente) {
    digitalWrite(PIN_LED_ROUGE, LOW);
    digitalWrite(PIN_LED_ORANGE, HIGH);
    digitalWrite(PIN_LED_VERTE, LOW);
  }
  else {
    digitalWrite(PIN_LED_ROUGE, LOW);
    digitalWrite(PIN_LED_ORANGE, LOW);
    digitalWrite(PIN_LED_VERTE, HIGH);
  }
}

// ==================== Gestion de la pédale ====================
void gererPedale() {
  if (!productionEnCours) {
    Serial.println("🚀 Lancement automatique de la production...");
    String body = "{\"shift\":\"" + currentShift + "\"}";
    String response = makeHTTPRequest("POST", "/api/lancer_automatique", body);

    if (response.indexOf("\"success\":true") > 0) {
      productionEnCours = true;
      // Force l’affichage immédiat de la LED rouge
      digitalWrite(PIN_LED_ROUGE, HIGH);
      digitalWrite(PIN_LED_ORANGE, LOW);
      digitalWrite(PIN_LED_VERTE, LOW);
      Serial.println("✅ Production lancée (LED rouge allumée)");
    } else {
      Serial.println("⚠️ Aucune tâche en attente.");
    }
  }
  else {
    Serial.println("➕ Incrémentation (+1)");
    String body = "{\"shift\":\"" + currentShift + "\"}";
    String response = makeHTTPRequest("POST", "/api/increment", body);

    if (response.indexOf("\"termine\":true") > 0) {
      Serial.println("🏁 Quantité atteinte ! Tâche terminée.");
      productionEnCours = false;
      // Clignotement vert pour signaler la fin
      for (int i = 0; i < 3; i++) {
        digitalWrite(PIN_LED_VERTE, HIGH);
        delay(100);
        digitalWrite(PIN_LED_VERTE, LOW);
        delay(100);
      }
      // Forcer une mise à jour complète pour rafraîchir la LED suivante
      mettreAJourSysteme();
    }
  }
}

// ==================== Gestion du bouton annulation ====================
void gererAnnulation() {
  if (productionEnCours) {
    Serial.println("➖ Décrémentation (-1)");
    String body = "{\"shift\":\"" + currentShift + "\"}";
    makeHTTPRequest("POST", "/api/decrement", body);
  } else {
    Serial.println("⏸️ Aucune production en cours, annulation ignorée.");
  }
}

// ==================== Loop principal ====================
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
