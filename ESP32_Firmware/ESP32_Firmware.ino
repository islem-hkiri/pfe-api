/*
   ESP32 Firmware - VERSION COMPLÈTE CORRIGÉE
   Communication avec API Flask sur PC
   Gestion complète: pédale, annulation, LEDs, API
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ================= CONFIGURATION WIFI =================
const char* ssid = "Infinix HOT 30";
const char* password = "chaima123";

// ================= CONFIGURATION SERVEUR LOCAL =================
// ⚠️ CHANGE CETTE IP AVEC L'IP DE TON PC ! ⚠️
// Pour trouver l'IP de ton PC:
// - Windows: cmd -> ipconfig -> "IPv4 Address"
// - Linux/Mac: ifconfig ou ip addr
const char* serverIP = "10.221.91.33";  // <--- CHANGE ICI AVEC L'IP DE TON PC !!!
const int serverPort = 5000;

// URL de base
String apiBaseUrl = "http://" + String(serverIP) + ":" + String(serverPort);

// ================= PINS =================
const int PIN_LIMIT_SWITCH = 32;    // Pédale (limit switch)
const int PIN_CANCEL_BUTTON = 12;   // Bouton annulation
const int PIN_LED_ROUGE = 14;       // LED Rouge (en cours)
const int PIN_LED_ORANGE = 27;      // LED Orange (en attente)
const int PIN_LED_VERTE = 26;       // LED Verte (disponible)

// ================= VARIABLES =================
String currentShift = "B";          // Shift A ou B (peut être changé)
bool productionEnCours = false;
int compteurLocal = 0;
int quantiteMax = 0;
int demandeId = 0;

// Gestion des erreurs de connexion
int erreurConsecutive = 0;
const int MAX_ERREURS = 5;

// Debounce
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 100;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

// Mise à jour périodique
unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 3000; // 3 secondes

// Timeout pour la production
unsigned long dernierIncrement = 0;
const unsigned long TIMEOUT_PRODUCTION = 300000; // 5 minutes sans activité

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  Serial.println("\n\n========================================");
  Serial.println("=== ESP32 DEMARRAGE - SOUDURE ULTRASONS ===");
  Serial.println("========================================\n");

  // Configuration des pins
  pinMode(PIN_LIMIT_SWITCH, INPUT_PULLUP);
  pinMode(PIN_CANCEL_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_VERTE, OUTPUT);

  // Éteindre toutes les LEDs au démarrage
  setLED(LOW, LOW, LOW);

  // Connexion WiFi
  Serial.print("📡 Connexion au WiFi: ");
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
    Serial.println("⚠️ Vérifiez vos identifiants WiFi");
  }

  delay(1000);

  // Récupérer l'état initial depuis l'API
  Serial.println("\n🔍 Récupération état initial...");
  mettreAJourEtatDepuisAPI();

  Serial.println("\n✅ ESP32 prêt !");
  Serial.println("🦶 Appuyez sur la pédale pour démarrer");
  Serial.println("❌ Bouton rouge pour annuler\n");
}

// ================= LED CONTROL =================
void setLED(bool rouge, bool orange, bool verte) {
  digitalWrite(PIN_LED_ROUGE, rouge ? HIGH : LOW);
  digitalWrite(PIN_LED_ORANGE, orange ? HIGH : LOW);
  digitalWrite(PIN_LED_VERTE, verte ? HIGH : LOW);

  // Affichage debug (optionnel - commenter si trop de bruit)
  // Serial.print("🎨 LED: ");
  // Serial.print(rouge ? "🔴" : "⚫");
  // Serial.print(orange ? "🟠" : "⚫");
  // Serial.println(verte ? "🟢" : "⚫");
}

// ================= APPEL API GÉNÉRIQUE =================
int appelAPI(String endpoint, String method, String body, String &response) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi non connecté!");
    Serial.println("🔄 Tentative de reconnexion...");
    WiFi.reconnect();
    delay(1000);
    if (WiFi.status() != WL_CONNECTED) {
      return -1;
    }
  }

  HTTPClient http;
  String url = apiBaseUrl + endpoint;

  Serial.print("📡 API Call: ");
  Serial.print(method);
  Serial.print(" ");
  Serial.println(url);

  if (body.length() > 0) {
    Serial.print("📦 Body: ");
    Serial.println(body);
  }

  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(1000); // Timeout 1 secondes

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
    Serial.print("📨 Réponse (code ");
    Serial.print(httpCode);
    Serial.print("): ");
    if (response.length() > 100) {
      Serial.println(response.substring(0, 100) + "...");
    } else {
      Serial.println(response);
    }
    erreurConsecutive = 0;
  } else {
    Serial.print("❌ Erreur HTTP: ");
    Serial.println(httpCode);
    Serial.println("⚠️ Vérifiez que le serveur Flask tourne sur le PC");
    erreurConsecutive++;
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
      int nouvelleQuantite = doc["quantite_requise"] | 0;
      int nouveauDemandeId = doc["demande_id"] | 0;

      Serial.println("\n--- 📊 ÉTAT REÇU ---");
      Serial.print("📌 Statut: ");
      Serial.print(statut);
      Serial.print(" | Qté: ");
      Serial.print(nouvelleQuantite);
      Serial.print(" | ID: ");
      Serial.println(nouveauDemandeId);

      // Mise à jour des LEDs selon le statut
      if (statut == "En cours") {
        if (!productionEnCours) {
          Serial.println("⚙️ Production EN COURS détectée!");
          productionEnCours = true;
          quantiteMax = nouvelleQuantite;
          demandeId = nouveauDemandeId;
          compteurLocal = 0;
          dernierIncrement = millis();
        }
        setLED(HIGH, LOW, LOW);  // Rouge
      }
      else if (statut == "En attente") {
        productionEnCours = false;
        setLED(LOW, HIGH, LOW);  // Orange
        Serial.println("⏳ En ATTENTE (tâche programmée)");
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

    // En cas d'erreur répétée, clignotement LED rouge pour alerter
    if (erreurConsecutive >= MAX_ERREURS) {
      Serial.println("🚨 TROP D'ERREURS! Vérifiez la connexion avec le PC!");
      for (int i = 0; i < 3; i++) {
        setLED(HIGH, LOW, LOW);
        delay(200);
        setLED(LOW, LOW, LOW);
        delay(200);
      }
      setLED(LOW, LOW, HIGH);
      erreurConsecutive = 0;
    }
  }
}

// ================= LANCER PRODUCTION =================
bool lancerProduction() {
  Serial.println("\n🚀 Tentative de lancement production...");

  String endpoint = "/api/lancer_automatique";
  String body = "{\"shift\":\"" + currentShift + "\"}";
  String response;

  int code = appelAPI(endpoint, "POST", body, response);

  if (code == 200) {
    DynamicJsonDocument doc(256);
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      bool success = doc["success"] | false;

      if (success) {
        demandeId = doc["demande_id"] | 0;
        quantiteMax = doc["quantite_requise"] | 0;

        Serial.println("✅ Production lancée avec succès!");
        Serial.print("📋 Demande ID: ");
        Serial.println(demandeId);
        Serial.print("🔢 Quantité à produire: ");
        Serial.println(quantiteMax);

        productionEnCours = true;
        compteurLocal = 0;
        dernierIncrement = millis();
        setLED(HIGH, LOW, LOW);  // Rouge

        return true;
      } else {
        String message = doc["message"] | "Aucune demande";
        Serial.print("❌ Échec lancement: ");
        Serial.println(message);
        return false;
      }
    } else {
      Serial.println("❌ Erreur parsing réponse");
      return false;
    }
  }

  Serial.println("❌ Échec communication avec API");
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
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      bool termine = doc["termine"] | false;
      int compteurActuel = doc["compteur"] | 0;

      compteurLocal = compteurActuel;
      dernierIncrement = millis();

      Serial.print("📊 Progression: ");
      Serial.print(compteurLocal);
      Serial.print(" / ");
      Serial.println(quantiteMax);

      if (termine) {
        Serial.println("🎉 PRODUCTION TERMINÉE!");
        productionEnCours = false;

        // Animation de succès
        for (int i = 0; i < 3; i++) {
          setLED(LOW, LOW, HIGH);
          delay(150);
          setLED(LOW, LOW, LOW);
          delay(150);
        }

        // Rafraîchir l'état
        mettreAJourEtatDepuisAPI();
        return true;
      }
      return false;
    }
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
    DynamicJsonDocument doc(256);
    deserializeJson(doc, response);
    int nouveauCompteur = doc["compteur"] | 0;
    compteurLocal = nouveauCompteur;

    Serial.print("➖ Décrémentation: ");
    Serial.print(compteurLocal);
    Serial.print(" / ");
    Serial.println(quantiteMax);

    return true;
  }

  Serial.println("❌ Échec décrémentation");
  return false;
}

// ================= GESTION PÉDALE =================
void gererPedale() {
  Serial.println("\n🦶🦶 PÉDALE APPUYÉE ! 🦶🦶");

  if (!productionEnCours) {
    // Démarrer nouvelle production
    Serial.println("🚀 Démarrage d'une nouvelle production...");

    // Feedback visuel: clignotement rapide
    setLED(LOW, HIGH, LOW);
    delay(100);
    setLED(HIGH, LOW, LOW);
    delay(100);

    if (lancerProduction()) {
      Serial.println("✅ Production DÉMARRÉE avec succès!");
    } else {
      Serial.println("❌ Aucune demande disponible ou erreur API");
      mettreAJourEtatDepuisAPI();
    }
  }
  else {
    // Incrémenter production en cours
    Serial.println("➕ Incrémentation de la production...");

    // Feedback visuel: flash vert rapide
    setLED(LOW, LOW, HIGH);
    delay(50);
    setLED(HIGH, LOW, LOW);

    bool termine = incrementerProduction();

    if (termine) {
      Serial.println("🏁 PRODUCTION COMPLÈTE!");
      // Animation déjà faite dans incrementerProduction
    } else {
      Serial.println("✅ Pièce comptée. Continuons!");
    }
  }
}

// ================= GESTION ANNULATION =================
void gererAnnulation() {
  Serial.println("\n❌❌ BOUTON ANNULATION APPUYÉ ! ❌❌");

  if (productionEnCours) {
    Serial.println("➖ Décrémentation de la production...");

    // Feedback visuel: clignotement orange
    for (int i = 0; i < 2; i++) {
      setLED(LOW, HIGH, LOW);
      delay(100);
      setLED(HIGH, LOW, LOW);
      delay(100);
    }

    if (decrementerProduction()) {
      Serial.println("✅ Annulation effectuée: -1 pièce");
    } else {
      Serial.println("❌ Erreur lors de l'annulation");
    }
  } else {
    Serial.println("⚠️ Aucune production en cours - Annulation ignorée");

    // Feedback: clignotement rapide orange pour indiquer erreur
    for (int i = 0; i < 2; i++) {
      setLED(LOW, HIGH, LOW);
      delay(50);
      setLED(LOW, LOW, LOW);
      delay(50);
    }
    mettreAJourEtatDepuisAPI();
  }
}

// ================= VÉRIFICATION TIMEOUT =================
void verifierTimeout() {
  if (productionEnCours && (millis() - dernierIncrement > TIMEOUT_PRODUCTION)) {
    Serial.println("\n⚠️ TIMEOUT: Aucune activité depuis 5 minutes!");
    Serial.println("🔄 Réinitialisation de l'état...");

    productionEnCours = false;
    mettreAJourEtatDepuisAPI();

    // Alerte visuelle: clignotement rouge
    for (int i = 0; i < 5; i++) {
      setLED(HIGH, LOW, LOW);
      delay(200);
      setLED(LOW, LOW, LOW);
      delay(200);
    }
    mettreAJourEtatDepuisAPI();
  }
}

// ================= LOOP PRINCIPAL =================
void loop() {
  // Lecture des entrées
  bool limitState = digitalRead(PIN_LIMIT_SWITCH);
  bool cancelState = digitalRead(PIN_CANCEL_BUTTON);

  // Détection front descendant (appui)
  if ((millis() - lastDebounceTime) > debounceDelay) {
    // Pédale: HIGH -> LOW (appui)
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

  // Mise à jour périodique de l'état (toutes les 3 secondes)
  if (millis() - lastLEDUpdate > LED_UPDATE_INTERVAL) {
    // Afficher l'état actuel périodiquement
    static int compteurAffichage = 0;
    if (compteurAffichage++ >= 5) { // Toutes les 15 secondes environ
      Serial.print("📊 État: ");
      if (productionEnCours) {
        Serial.print("EN COURS | ");
        Serial.print(compteurLocal);
        Serial.print("/");
        Serial.println(quantiteMax);
      } else {
        Serial.println("LIBRE/ATTENTE");
      }
      compteurAffichage = 0;
    }

    mettreAJourEtatDepuisAPI();
    lastLEDUpdate = millis();
  }

  // Vérifier le timeout de production
  verifierTimeout();

  delay(50);  // Petit délai pour stabilité
}
