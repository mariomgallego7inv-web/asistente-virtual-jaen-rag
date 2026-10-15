import os
import json

# Ruta de tu archivo de resultados
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
ARCHIVO_RESULTADOS = os.path.join(PROJECT_ROOT, "results", "metricas_generadores.json")

def analizar_resultados():
    print("📊 Analizando el JSON de Ragas...")
    
    try:
        with open(ARCHIVO_RESULTADOS, 'r', encoding='utf-8') as f:
            datos = json.load(f)
    except FileNotFoundError:
        print("❌ No se encontró el archivo. Asegúrate de que la ruta es correcta.")
        return

    # Diccionario para acumular las notas y contar cuántas hay
    estadisticas = {}

    for pregunta in datos:
        modelos = pregunta.get("evaluacion_modelos", {})
        
        for nombre_modelo, notas in modelos.items():
            # Si el modelo no está en el diccionario, lo creamos
            if nombre_modelo not in estadisticas:
                estadisticas[nombre_modelo] = {
                    "suma_relevancia": 0, "conteo_relevancia": 0,
                    "suma_fidelidad": 0, "conteo_fidelidad": 0
                }
            
            # Extraemos las notas
            rel = notas.get("Answer_Relevancy")
            fid = notas.get("Faithfulness")
            
            # Sumamos solo si no dio ERROR (si es un número)
            if isinstance(rel, (int, float)):
                estadisticas[nombre_modelo]["suma_relevancia"] += rel
                estadisticas[nombre_modelo]["conteo_relevancia"] += 1
                
            if isinstance(fid, (int, float)):
                estadisticas[nombre_modelo]["suma_fidelidad"] += fid
                estadisticas[nombre_modelo]["conteo_fidelidad"] += 1

    # Imprimir la tabla de resultados finales
    print("\n" + "="*60)
    print("🏆 RANKING FINAL DE MODELOS (MEDIAS GLOBALES)")
    print("="*60)
    print(f"{'MODELO':<25} | {'RELEVANCIA MEDIA':<15} | {'FIDELIDAD MEDIA'}")
    print("-" * 60)

    for nombre_modelo, stats in estadisticas.items():
        # Calculamos la media (evitando dividir por cero si todas dieron error)
        if stats["conteo_relevancia"] > 0:
            media_rel = stats["suma_relevancia"] / stats["conteo_relevancia"]
        else:
            media_rel = 0.0
            
        if stats["conteo_fidelidad"] > 0:
            media_fid = stats["suma_fidelidad"] / stats["conteo_fidelidad"]
        else:
            media_fid = 0.0

        # Imprimimos la fila con 4 decimales
        print(f"{nombre_modelo:<25} | {media_rel:.4f}           | {media_fid:.4f}")

    print("="*60)
    print(f"Total de preguntas analizadas: {len(datos)}")

if __name__ == "__main__":
    analizar_resultados()