/*
 * ESP32 Firmware - VERSION SIMPLIFIEE (STABLE)
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
int compteurLocal = 0;
int quantiteMax = 0;
int demandeId = 0;

unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 100;
bool lastLimitState = HIGH;
bool lastCancelState = HIGH;

unsigned long lastLEDUpdate = 0;
const unsigned long LED_UPDATE_INTERVAL = 3000;

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

  // Connexion WiFi
  Serial.print("Connexion WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connecte !");
  Serial.print("Adresse IP: ");
  Serial.println(WiFi.localIP());

  delay(1000);
  mettreAJourEtatDepuisAPI();
}

// ================= LED CONTROL =================
void setLED(bool r, bool o, bool v) {
  digitalWrite(PIN_LED_ROUGE, r);
  digitalWrite(PIN_LED_ORANGE, o);
  digitalWrite(PIN_LED_VERTE, v);
  Serial.print("LED: R=");
  Serial.print(r);
  Serial.print(" O=");
  Serial.print(o);
  Serial.print(" V=");
  Serial.println(v);
}

// ================= RECUPERER ETAT DEPUIS API =================
void mettreAJourEtatDepuisAPI() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  String url = "https://" + String(serverHost) + "/api/etat?shift=" + currentShift;
  Serial.print("Appel API: ");
  Serial.println(url);
  
  https.begin(client, url);
  int code = https.GET();
  
  if (code == 200) {
    String response = https.getString();
    Serial.print("Reponse API: ");
    Serial.println(response);
    
    DynamicJsonDocument doc(512);
    DeserializationError error = deserializeJson(doc, response);
    
    if (!error) {
      String statut = doc["statut"].as<String>();
      quantiteMax = doc["quantite_requise"] | 0;
      demandeId = doc["demande_id"] | 0;
      
      Serial.print("Statut: ");
      Serial.print(statut);
      Serial.print(" | Quantite max: ");
      Serial.print(quantiteMax);
      Serial.print(" | Demande ID: ");
      Serial.println(demandeId);
      
      // Mise a jour des LEDs selon le statut
      if (statut == "En cours") {
        productionEnCours = true;
        setLED(HIGH, LOW, LOW);  // Rouge
        Serial.println(">>> Production EN COURS");
      } 
      else if (statut == "En attente") {
        productionEnCours = false;
        setLED(LOW, HIGH, LOW);  // Orange
        Serial.println(">>> En ATTENTE");
      } 
      else {
        productionEnCours = false;
        setLED(LOW, LOW, HIGH);  // Vert
        Serial.println(">>> LIBRE");
      }
    } else {
      Serial.print("Erreur parsing JSON: ");
      Serial.println(error.c_str());
    }
  } else {
    Serial.print("Erreur HTTP: ");
    Serial.println(code);
  }
  
  https.end();
}

// ================= LANCER PRODUCTION =================
bool lancerProduction() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;
  
  String url = "https://" + String(serverHost) + "/api/lancer_automatique";
  https.begin(client, url);
  https.addHeader("Content-Type", "application/json");
  
  String body = "{\"shift\":\"" + currentShift + "\"}";
  int code = https.POST(body);
  String response = https.getString();
  
  Serial.print("Lancer production - Code: ");
  Serial.print(code);
  Serial.print(" | Reponse: ");
  Serial.println(response);
  
  https.end();
  
  if (code == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, response);
    return doc["success"] | false;
  }
  return false;
}

// ================= INCREMENT =================
bool incrementerProduction() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;
  
  String url = "https://" + String(serverHost) + "/api/increment";
  https.begin(client, url);
  https.addHeader("Content-Type", "application/json");
  
  String body = "{\"shift\":\"" + currentShift + "\"}";
  int code = https.POST(body);
  String response = https.getString();
  
  Serial.print("Increment - Code: ");
  Serial.print(code);
  Serial.print(" | Reponse: ");
  Serial.println(response);
  
  https.end();
  
  if (code == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, response);
    bool termine = doc["termine"] | false;
    return termine;
  }
  return false;
}

// ================= DECREMENT =================
void decrementerProduction() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;
  
  String url = "https://" + String(serverHost) + "/api/decrement";
  https.begin(client, url);
  https.addHeader("Content-Type", "application/json");
  
  String body = "{\"shift\":\"" + currentShift + "\"}";
  int code = https.POST(body);
  String response = https.getString();
  
  Serial.print("Decrement - Code: ");
  Serial.print(code);
  Serial.print(" | Reponse: ");
  Serial.println(response);
  
  https.end();
}

// ================= GESTION PEDALE =================
void gererPedale() {
  Serial.println(">>> Pedale appuyee <<<");
  
  if (!productionEnCours) {
    // Demarrer nouvelle production
    Serial.println("Tentative de demarrage production...");
    setLED(HIGH, LOW, LOW);  // Rouge immediat
    
    if (lancerProduction()) {
      productionEnCours = true;
      Serial.println("Production DEMARREE avec succes !");
      // Attendre un peu et rafraichir l'etat
      delay(500);
      mettreAJourEtatDepuisAPI();
    } else {
      Serial.println("ECHEC demarrage - Aucune demande en attente!");
      productionEnCours = false;
      mettreAJourEtatDepuisAPI();
    }
  } 
  else {
    // Incrementer production en cours
    Serial.println("Incrementation production...");
    bool termine = incrementerProduction();
    
    if (termine) {
      Serial.println(">>> PRODUCTION TERMINEE ! <<<");
      productionEnCours = false;
      
      // Clignotement LED VERTE 3 fois
      for (int i = 0; i < 3; i++) {
        setLED(LOW, LOW, HIGH);
        delay(200);
        setLED(LOW, LOW, LOW);
        delay(200);
      }
      
      // Rafraichir l'etat
      mettreAJourEtatDepuisAPI();
    } else {
      Serial.println("Increment reussi, production continue...");
      // Faire clignoter LED VERTE rapidement pour confirmer
      setLED(LOW, LOW, HIGH);
      delay(100);
      setLED(HIGH, LOW, LOW);
    }
  }
}

// ================= GESTION ANNULATION =================
void gererAnnulation() {
  Serial.println(">>> Bouton ANNULATION appuye <<<");
  
  if (productionEnCours) {
    decrementerProduction();
    Serial.println("Decrement effectue");
    
    // Clignotement LED ORANGE pour confirmer
    for (int i = 0; i < 2; i++) {
      setLED(LOW, HIGH, LOW);
      delay(100);
      setLED(HIGH, LOW, LOW);
      delay(100);
    }
  } else {
    Serial.println("Aucune production en cours - Annulation ignoree");
  }
}

// ================= LOOP PRINCIPAL =================
void loop() {
  bool limitState = digitalRead(PIN_LIMIT_SWITCH);
  bool cancelState = digitalRead(PIN_CANCEL_BUTTON);

  // Detection front descendant (appui)
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

  // Mise a jour periodique de l'etat
  if (millis() - lastLEDUpdate > LED_UPDATE_INTERVAL) {
    Serial.println("--- Mise a jour periodique ---");
    mettreAJourEtatDepuisAPI();
    lastLEDUpdate = millis();
  }

  delay(50);
}
