/*
 * ESP32 Firmware - VERSION FINALE (STABLE INDUSTRIEL) - CORRIGÉE
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
String currentShift = "B";   // Peut être changé en "A" si besoin
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
  Serial.println("\n WiFi connecté");

  // Synchronisation de l'état de production au démarrage
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

  https.end();
  return res;
}

// ================= LED CONTROL =================
void setLED(bool r, bool o, bool v) {
  digitalWrite(PIN_LED_ROUGE, r);
  digitalWrite(PIN_LED_ORANGE, o);
  digitalWrite(PIN_LED_VERTE, v);
}

// ================= SYNCHRONISATION DÉMARRAGE =================
void synchroniserEtatProduction() {
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
    
    if (statut.indexOf("En cours") >= 0) {
      productionEnCours = true;
      setLED(HIGH, LOW, LOW);   // Rouge : production active
      Serial.println("Production déjà en cours (récupéré depuis API)");
    } else {
      productionEnCours = false;
      if (statut.indexOf("En attente") >= 0) {
        setLED(LOW, HIGH, LOW); // Orange : en attente
      } else {
        setLED(LOW, LOW, HIGH); // Vert : libre
      }
    }
  } else {
    Serial.println("Impossible de synchroniser l'état au démarrage");
  }
  https.end();
}

// ================= UPDATE FROM API (LEDS) =================
void mettreAJourSysteme() {
  // Ne pas changer les LEDs si la production est en cours (déjà rouge)
  if (productionEnCours) return;

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

    if (statut.indexOf("En attente") >= 0) {
      setLED(LOW, HIGH, LOW);   // Orange
    } else if (statut.indexOf("En cours") >= 0) {
      // Cas anormal : productionEnCours devrait être true, mais on sécurise
      productionEnCours = true;
      setLED(HIGH, LOW, LOW);   // Rouge
    } else {
      setLED(LOW, LOW, HIGH);   // Vert : libre ou terminé
    }
  }
  https.end();
}

// ================= PEDALE =================
void gererPedale() {
  if (!productionEnCours) {
    // Démarrage production
    Serial.println("START");
    setLED(HIGH, LOW, LOW);   // Rouge immédiat
    productionEnCours = true;
    postRequest("/api/lancer_automatique");
  } else {
    // Incrément
    Serial.println("INCREMENT");
    String res = postRequest("/api/increment");
    
    // Analyse JSON pour savoir si la production est terminée
    DynamicJsonDocument doc(256);
    deserializeJson(doc, res);
    bool termine = doc["termine"] | false;
    
    if (termine) {
      Serial.println("FIN");
      productionEnCours = false;
      // Clignotement vert
      for (int i = 0; i < 3; i++) {
        setLED(LOW, LOW, HIGH);
        delay(150);
        setLED(LOW, LOW, LOW);
        delay(150);
      }
      // Mise à jour LED selon l'état API
      mettreAJourSysteme();
    }
  }
}

// ================= CANCEL =================
void gererAnnulation() {
  if (productionEnCours) {
    Serial.println("➖ DECREMENT");
    postRequest("/api/decrement");
  }
}

// ================= LOOP =================
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
