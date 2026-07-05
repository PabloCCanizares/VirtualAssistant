WEEKLY_SUMMARY_PROMPT = (
    "Con el contexto del usuario y summary_metrics, genera un resumen de la semana. "
    "Usa summary_metrics como fuente principal para numeros: tareas completadas, pendientes, "
    "vencidas, carga productiva y foco. "
    "Dormir, comer, deporte, salud, ocio, social y logistica son contexto separado: "
    "pueden explicar energia o recuperacion, pero nunca cuentan como productividad. "
    "Incluye: 1) avances clave, 2) pendientes importantes con fecha limite cercana, "
    "3) riesgos o bloqueos, 4) una recomendacion concreta para la proxima semana. "
    "Si falta una metrica, dilo como dato no registrado en vez de inventarlo. "
    "No devuelvas el objeto ID."
)
