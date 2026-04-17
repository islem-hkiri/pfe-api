/*
 * ESP32 Firmware - VERSION FINALE (STABLE INDUSTRIEL) - CORRIGEE
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

// ================= WIFI =================
const char* ssid = "BEE HUAWEI-1CB0";
const char* password = "485754439C621CB0";

// ================= API =================
const char* serverHost = "pfe-api-vure.onrender.com";

// ================= PINS =================
const int PIN_LIMIT_SWITCH = 13;
const int PIN_CANCEL_BUTTON = 12;
const int PIN_LED_ROUGE = 14;
const int PIN_LED_ORANGE = 27;
const int PIN_LED_VERTE = 26;

// ================= VARIABLES =================
String currentShift = "B";
bool productionEnCours = false;

unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 100;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 2000;

// ================= SETUP =================
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
  Serial.println("\nWiFi connecte");

  delay(1000);
  synchroniserEtatProduction();
}

// ================= HTTP =================
String postRequest(String endpoint) {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + endpoint;
  https.begin(client, url);
  https.addHeader("Content-Type", "application/json");

  int code = https.POST("{\"shift\":\"" + currentShift + "\"}");
  String res = https.getString();
  
  Serial.print("Reponse API (");
  Serial.print(endpoint);
  Serial.print("): ");
  Serial.println(res);

  https.end();
  return res;
}

// ================= LED CONTROL =================
void setLED(bool r, bool o, bool v) {
  digitalWrite(PIN_LED_ROUGE, r);
  digitalWrite(PIN_LED_ORANGE, o);
  digitalWrite(PIN_LED_VERTE, v);
}

// ================= SYNCHRONISATION DEMARRAGE =================
void synchroniserEtatProduction() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + "/api/etat?shift=" + currentShift;
  https.begin(client, url);
  int code = https.GET();
  if (code == 200) {
    String response = https.getString();
    Serial.print("Etat initial: ");
    Serial.println(response);
    
    DynamicJsonDocument doc(1024);
    deserializeJson(doc, response);
    String statut = doc["statut"] | "";
    int quantiteRequise = doc["quantite_requise"] | 0;
    
    Serial.print("Statut recu: '");
    Serial.print(statut);
    Serial.print("' Quantite: ");
    Serial.println(quantiteRequise);
    
    if (statut == "En cours") {
      productionEnCours = true;
      setLED(HIGH, LOW, LOW);
      Serial.println("Production deja en cours");
    } else {
      productionEnCours = false;
      if (statut == "En attente") {
        setLED(LOW, HIGH, LOW);
        Serial.println("Mode: En attente");
      } else {
        setLED(LOW, LOW, HIGH);
        Serial.println("Mode: Libre");
      }
    }
  } else {
    Serial.print("Erreur HTTP: ");
    Serial.println(code);
    Serial.println("Impossible de synchroniser l'etat au demarrage");
  }
  https.end();
}

// ================= UPDATE FROM API (LEDS) =================
void mettreAJourSysteme() {
  if (productionEnCours) {
    Serial.println("Production en cours, mise a jour LED ignoree");
    return;
  }

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + "/api/etat?shift=" + currentShift;
  https.begin(client, url);
  int code = https.GET();
  if (code == 200) {
    String response = https.getString();
    DynamicJsonDocument doc(1024);
    deserializeJson(doc, response);
    String statut = doc["statut"] | "";

    Serial.print("Mise a jour LED - Statut: ");
    Serial.println(statut);

    if (statut == "En attente") {
      setLED(LOW, HIGH, LOW);
      Serial.println("LED -> ORANGE (En attente)");
    } else if (statut == "En cours") {
      productionEnCours = true;
      setLED(HIGH, LOW, LOW);
      Serial.println("LED -> ROUGE (En cours)");
    } else {
      setLED(LOW, LOW, HIGH);
      Serial.println("LED -> VERT (Libre)");
    }
  } else {
    Serial.print("Erreur GET etat: ");
    Serial.println(code);
  }
  https.end();
}

// ================= PEDALE =================
void gererPedale() {
  if (!productionEnCours) {
    Serial.println("===== DEMARRAGE PRODUCTION =====");
    setLED(HIGH, LOW, LOW);
    productionEnCours = true;
    String response = postRequest("/api/lancer_automatique");
    
    // Verifier si le demarrage a reussi
    DynamicJsonDocument doc(256);
    deserializeJson(doc, response);
    bool success = doc["success"] | false;
    
    if (success) {
      Serial.println("Production demarree avec succes");
    } else {
      Serial.println("Erreur: Aucune demande en attente");
      productionEnCours = false;
      mettreAJourSysteme();
    }
  } else {
    Serial.println("===== INCREMENT =====");
    String res = postRequest("/api/increment");
    
    DynamicJsonDocument doc(256);
    deserializeJson(doc, res);
    bool success = doc["success"] | false;
    bool termine = doc["termine"] | false;
    
    Serial.print("Success: ");
    Serial.print(success);
    Serial.print(" | Termine: ");
    Serial.println(termine);
    
    if (termine) {
      Serial.println("===== PRODUCTION TERMINEE =====");
      productionEnCours = false;
      // Clignotement vert 3 fois
      for (int i = 0; i < 3; i++) {
        setLED(LOW, LOW, HIGH);
        delay(200);
        setLED(LOW, LOW, LOW);
        delay(200);
      }
      mettreAJourSysteme();
    }
  }
}

// ================= CANCEL =================
void gererAnnulation() {
  if (productionEnCours) {
    Serial.println("===== DECREMENT =====");
    String res = postRequest("/api/decrement");
    Serial.print("Reponse decrement: ");
    Serial.println(res);
  } else {
    Serial.println("Annulation ignoree: pas de production en cours");
  }
}

// ================= LOOP =================
void loop() {
  bool limitState = digitalRead(PIN_LIMIT_SWITCH);
  bool cancelState = digitalRead(PIN_CANCEL_BUTTON);

  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (lastLimitState == HIGH && limitState == LOW) {
      Serial.println("*** Pedale appuyee ***");
      gererPedale();
      lastDebounceTime = millis();
    }
    if (lastCancelState == HIGH && cancelState == LOW) {
      Serial.println("*** Bouton cancel appuye ***");
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
