# init_db_once.py - Exécute ceci UNE SEULE FOIS au début
import database_v2

print("=" * 50)
print("🏗️ INITIALISATION DE LA BASE DE DONNÉES")
print("=" * 50)

result = database_v2.manual_sync()
print(f"Résultat: {result}")

print("\n✅ Base prête! Tu peux maintenant lancer l'application.")