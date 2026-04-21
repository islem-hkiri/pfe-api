/*
   ESP32 Firmware - VERSION LOCALE (IP fixe du PC)
   Yekhdem bil API Flask locale 3al port 5000
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ================= CONFIGURATION WIFI =================
const char* ssid = "Infinix HOT 30";
const char* password = "chaima123";

// ================= CONFIGURATION SERVEUR LOCAL =================
// !! CHANGE CETTE IP AVEC L'IP DE TON PC !!
// Pour trouver l'IP de ton PC:
// - Windows: ouvre cmd tape "ipconfig" -> regarde "IPv4 Address"
// - Linux/Mac: tape "ifconfig" ou "ip addr"
const char* serverIP = "10.221.91.33";  // <--- CHANGE ICI AVEC IP DE TON PC
const int serverPort = 5000;              // Port Flask API

// URL de base pour l'API locale
String apiBaseUrl = "http://" + String(serverIP) + ":" + String(serverPort);

// ================= PINS =================
const int PIN_LIMIT_SWITCH = 34;    // Pedale (limit switch)
const int PIN_CANCEL_BUTTON = 12;   // Bouton annulation
const int PIN_LED_ROUGE = 14;       // LED Rouge (en cours)
const int PIN_LED_ORANGE = 27;      // LED Orange (en attente)
const int PIN_LED_VERTE = 26;       // LED Verte (disponible)

// ================= VARIABLES =================
String currentShift = "B";          // Shift A ou B (à modifier selon besoin)
bool productionEnCours = false;
int compteurLocal = 0;
int quantiteMax = 0;
int demandeId = 0;

// Debounce
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 100;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

// Mise à jour périodique
unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 3000; // 3 secondes

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  Serial.println("\n\n=== ESP32 DEMARRAGE ===");

  // Configuration des pins
  pinMode(PIN_LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(PIN_CANCEL_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_VERTE, OUTPUT);

  // Éteindre toutes les LEDs au démarrage
  setLED(LOW, LOW, LOW);

  // Connexion WiFi
  Serial.print("Connexion au WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi connecté !");
    Serial.print("📡 IP ESP32: ");
    Serial.println(WiFi.localIP());
    Serial.print("🎯 Serveur API: ");
    Serial.println(apiBaseUrl);
  } else {
    Serial.println("\n❌ Échec connexion WiFi!");
  }

  delay(1000);

  // Récupérer l'état initial depuis l'API
  mettreAJourEtatDepuisAPI();
}

// ================= LED CONTROL =================
void setLED(bool rouge, bool orange, bool verte) {
  digitalWrite(PIN_LED_ROUGE, rouge);
  digitalWrite(PIN_LED_ORANGE, orange);
  digitalWrite(PIN_LED_VERTE, verte);

  Serial.print("🎨 LED: R=");
  Serial.print(rouge ? "🔴" : "⚫");
  Serial.print(" O=");
  Serial.print(orange ? "🟠" : "⚫");
  Serial.print(" V=");
  Serial.println(verte ? "🟢" : "⚫");
}

// ================= APPEL API GENERIQUE =================
int appelAPI(String endpoint, String method, String body, String &response) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi non connecté!");
    return -1;
  }

  HTTPClient http;
  String url = apiBaseUrl + endpoint;

  Serial.print("📡 Appel API: ");
  Serial.print(method);
  Serial.print(" ");
  Serial.println(url);

  if (body.length() > 0) {
    Serial.print("📦 Body: ");
    Serial.println(body);
  }

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  int httpCode;
  if (method == "GET") {
    httpCode = http.GET();
  } else if (method == "POST") {
    httpCode = http.POST(body);
  } else {
    http.end();
    return -1;
  }

  if (httpCode > 0) {
    response = http.getString();
    Serial.print("📨 Reponse (code ");
    Serial.print(httpCode);
    Serial.print("): ");
    Serial.println(response.substring(0, 200)); // Afficher début seulement
  } else {
    Serial.print("❌ Erreur HTTP: ");
    Serial.println(httpCode);
    response = "";
  }

  http.end();
  return httpCode;
}

// ================= RÉCUPÉRER ÉTAT DEPUIS API =================
void mettreAJourEtatDepuisAPI() {
  String endpoint = "/api/etat?shift=" + currentShift;
  String response;

  int code = appelAPI(endpoint, "GET", "", response);

  if (code == 200 && response.length() > 0) {
    DynamicJsonDocument doc(512);
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      String statut = doc["statut"] | "Libre";
      quantiteMax = doc["quantite_requise"] | 0;
      demandeId = doc["demande_id"] | 0;

      Serial.println("--- ÉTAT REÇU ---");
      Serial.print("📌 Statut: ");
      Serial.print(statut);
      Serial.print(" | Quantité max: ");
      Serial.print(quantiteMax);
      Serial.print(" | Demande ID: ");
      Serial.println(demandeId);

      // Mise à jour des LEDs selon le statut
      if (statut == "En cours") {
        productionEnCours = true;
        setLED(HIGH, LOW, LOW);  // Rouge
        Serial.println("⚙️ Production EN COURS");
      }
      else if (statut == "En attente") {
        productionEnCours = false;
        setLED(LOW, HIGH, LOW);  // Orange
        Serial.println("⏳ En ATTENTE");
      }
      else {
        productionEnCours = false;
        setLED(LOW, LOW, HIGH);  // Vert
        Serial.println("✅ LIBRE (Disponible)");
      }
    } else {
      Serial.print("❌ Erreur parsing JSON: ");
      Serial.println(error.c_str());
    }
  } else {
    Serial.print("❌ Échec récupération état (code: ");
    Serial.print(code);
    Serial.println(")");
    // En cas d'erreur, on garde l'état actuel
  }
}

// ================= LANCER PRODUCTION =================
bool lancerProduction() {
  String endpoint = "/api/lancer_automatique";
  String body = "{\"shift\":\"" + currentShift + "\"}";
  String response;

  int code = appelAPI(endpoint, "POST", body, response);

  if (code == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, response);
    bool success = doc["success"] | false;

    if (success) {
      Serial.println("✅ Production lancée avec succès!");
      // Récupérer les infos de la tâche
      demandeId = doc["demande_id"] | 0;
      quantiteMax = doc["quantite_requise"] | 0;
      return true;
    } else {
      Serial.println("❌ Aucune demande en attente!");
      return false;
    }
  }

  Serial.println("❌ Échec lancement production");
  return false;
}

// ================= INCREMENTER PRODUCTION =================
bool incrementerProduction() {
  String endpoint = "/api/increment";
  String body = "{\"shift\":\"" + currentShift + "\"}";
  String response;

  int code = appelAPI(endpoint, "POST", body, response);

  if (code == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, response);
    bool termine = doc["termine"] | false;
    int compteurActuel = doc["compteur"] | 0;

    Serial.print("📊 Compteur actuel: ");
    Serial.print(compteurActuel);
    Serial.print(" / ");
    Serial.println(quantiteMax);

    if (termine) {
      Serial.println("🎉 PRODUCTION TERMINÉE!");
      return true;
    }
    return false;
  }

  Serial.println("❌ Échec incrémentation");
  return false;
}

// ================= DÉCREMENTER PRODUCTION =================
bool decrementerProduction() {
  String endpoint = "/api/decrement";
  String body = "{\"shift\":\"" + currentShift + "\"}";
  String response;

  int code = appelAPI(endpoint, "POST", body, response);

  if (code == 200) {
    Serial.println("✅ Décrémentation effectuée");
    return true;
  }

  Serial.println("❌ Échec décrémentation");
  return false;
}

// ================= GESTION PEDALE =================
void gererPedale() {
  Serial.println("\n🦶 PEDALE APPUYÉE !");

  if (!productionEnCours) {
    // Démarrer nouvelle production
    Serial.println("🚀 Tentative de démarrage...");
    setLED(HIGH, LOW, LOW);  // Rouge immédiatement

    if (lancerProduction()) {
      productionEnCours = true;
      Serial.println("✅ Production DÉMARRÉE !");
      delay(300);
      mettreAJourEtatDepuisAPI();
    } else {
      Serial.println("❌ Aucune demande disponible");
      productionEnCours = false;
      mettreAJourEtatDepuisAPI();
    }
  }
  else {
    // Incrémenter production en cours
    Serial.println("➕ Incrémentation...");

    // Feedback visuel: clignotement rapide
    setLED(LOW, LOW, HIGH);
    delay(50);
    setLED(HIGH, LOW, LOW);

    bool termine = incrementerProduction();

    if (termine) {
      Serial.println("🏁 PRODUCTION TERMINÉE !");
      productionEnCours = false;

      // Animation de succès: clignotement vert 3 fois
      for (int i = 0; i < 3; i++) {
        setLED(LOW, LOW, HIGH);
        delay(150);
        setLED(LOW, LOW, LOW);
        delay(150);
      }

      mettreAJourEtatDepuisAPI();
    } else {
      Serial.println("✅ Incrément réussi");
    }
  }
}

// ================= GESTION ANNULATION =================
void gererAnnulation() {
  Serial.println("\n❌ BOUTON ANNULATION APPUYÉ !");

  if (productionEnCours) {
    Serial.println("➖ Décrémentation...");

    // Feedback visuel: clignotement orange
    for (int i = 0; i < 2; i++) {
      setLED(LOW, HIGH, LOW);
      delay(100);
      setLED(HIGH, LOW, LOW);
      delay(100);
    }

    if (decrementerProduction()) {
      Serial.println("✅ -1 effectué");
    }
  } else {
    Serial.println("⚠️ Aucune production en cours - Annulation ignorée");
  }
}

// ================= LOOP PRINCIPAL =================
void loop() {
  bool limitState = digitalRead(PIN_LIMIT_SWITCH);
  bool cancelState = digitalRead(PIN_CANCEL_BUTTON);

  // Détection front descendant (appui)
  if ((millis() - lastDebounceTime) > debounceDelay) {
    // Pedale: HIGH -> LOW (appui)
    if (lastLimitState == HIGH && limitState == LOW) {
      gererPedale();
      lastDebounceTime = millis();
    }

    // Bouton annulation: HIGH -> LOW (appui)
    if (lastCancelState == HIGH && cancelState == LOW) {
      gererAnnulation();
      lastDebounceTime = millis();
    }
  }

  lastLimitState = limitState;
  lastCancelState = cancelState;

  // Mise à jour périodique de l'état
  if (millis() - lastLEDUpdate > LED_UPDATE_INTERVAL) {
    Serial.println("\n--- 🔄 Mise à jour périodique ---");
    mettreAJourEtatDepuisAPI();
    lastLEDUpdate = millis();
  }

  delay(50);
}
