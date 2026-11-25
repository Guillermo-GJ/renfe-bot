"""This module contains the messages that the bot sends to the user"""

from typing import List

from models import TrainRideRecord, StationRecord

user_messages = {
    "welcome": "Hola {}. Bienvenido a tu bot de Renfe. Te ayudaré a encontrar billetes de tren para tus viajes. Para empezar, escribe /ayuda para ver los comandos disponibles.",
    "help": "/buscar - Busca billetes de tren\n/repetir - Repite tu última búsqueda (puedes cambiar el día o la hora)\n/estado - Te dice si tu búsqueda sigue activa y cómo va\n/cancelar - Cancela la búsqueda en curso\n/prueba - Te manda un aviso de ejemplo a los 15 s (o /prueba 60 para esperar 60 s)\n/ayuda - Muestra los comandos disponibles",
    "cancel": "La búsqueda ha sido cancelada.",
    "cancel_params": "Reiniciando el proceso de búsqueda, usa /buscar para empezar de nuevo",
    "search_already_running": "Ya hay una búsqueda en curso, por favor espera o utiliza /cancelar para cancelarla",
    "start": "🚉 ¿Desde qué estación sales?",
    "destination": "🚉 ¿A qué estación vas?",
    "station_invalid": "No encuentro ninguna estación parecida. Escribe el nombre como aparece en Renfe, por ejemplo: «Madrid (Todas)», «Barcelona-Sants», «Valencia Joaquín Sorolla» o «Zaragoza-Delicias».",
    "destination_date": "📅 ¿Qué día sales? Elígelo en el calendario o escríbelo con la hora (ej. 14/03/2027 09:30).",
    "return_date": "📅 ¿Qué día vuelves? Elígelo en el calendario o escríbelo con la hora (ej. 01/12/2026 18:00).",
    "exact_time": "⏰ ¿Quieres vigilar solo el tren que sale exactamente a esa hora? (sí/no)",
    "needs_return": "🔙 ¿Necesitas billete de vuelta?",
    "needs_filter": "🔍 ¿Quieres filtrar los resultados (precio, duración)?",
    "max_price": "💵 ¿Precio máximo? (introduce 0 si no quieres filtrar por precio)",
    "max_duration": "⏳ ¿Duración máxima? (introduce 0 si no quieres filtrar por duración)",
    "searching": "🔎 Buscando billetes...",
    "station_not_found": "No encuentro la estación «{}». ¿Quizás es una de estas?\n{}\n\nPulsa un botón o escríbela de nuevo.",
    "confirm_date": "Vale, a partir de esta fecha y hora: {}",
    "wrong_date": "No he entendido la fecha. Escríbela así:\n• 14/03/2027 09:30\n• 14/03 09:30\n• 14 de marzo a las 09:30\nSi no pones hora, buscaré desde las 00:00.",
    "past_date": "Esa fecha ya ha pasado. Escribe una fecha de hoy en adelante, por ejemplo: 14/03/2027 09:30",
    "wrong_number": "Número incorrecto, introdúcelo de nuevo.",
    "invalid_filter": "El filtro introducido no es válido o no se encontró ningún tren con estos parámetros, por favor, inténtalo de nuevo.",
    "invalid_dwr_token": "Si esto ha ocurrido, Renfe ha actualizado por fin su web. Por favor, abre una issue en github para que pueda revisarlo.",
    "search_paused": "⏸️ El bot se ha detenido y tu búsqueda queda en pausa: {}.\nLa retomaré automáticamente en cuanto vuelva a arrancar.",
    "search_resumed": "▶️ He vuelto a arrancar y retomo tu búsqueda: {}.\nUsa /cancelar si ya no la necesitas.",
    "station_ok": "✅ Destino: {}",
    "ok": "👍",
    "pick_time": "🕒 Trenes de {} a {} ese día. Pulsa la hora de salida del que quieras vigilar, o escribe una hora (ej. 09:30) para vigilar todos desde esa hora:",
    "pick_time_unknown": "🕒 No he podido ver los horarios de ese día. Escribe una hora (ej. 09:30) para vigilar los trenes desde esa hora, o pulsa el botón:",
    "any_train": "✅ Vigilaré cualquier tren del {}.",
    "confirm_return": "Vale, vuelta a partir de: {}",
    "wrong_time": "No he entendido la hora. Escríbela así: 09:30 (o pulsa uno de los botones).",
    "old_buttons": "Estos botones ya no están activos. Usa los del último mensaje.",
    "nothing_to_repeat": "Todavía no has hecho ninguna búsqueda. Usa /buscar para empezar.",
    "repeat_question": "🔁 Tu última búsqueda fue:\n{}\n\n¿La repito igual o quieres cambiar algo?",
    "repeat_past_day": "Ese día ya ha pasado, elige otro:",
    "repeat_pick": "Pulsa uno de los botones, o usa /cancelar.",
    "status_none": "💤 No tienes ninguna búsqueda activa. Usa /buscar o /repetir para empezar una.",
    "status_running": "✅ Tu búsqueda está activa:\n{search}\n\n• Vigilando sin parar desde: {since}\n• Consultas a Renfe: {checks} (una por minuto)\n• Última consulta: {last}\n• Resultado: {result}",
    "status_failing": "⚠️ Llevo {} intentos seguidos sin poder consultar Renfe. Sigo intentándolo.",
    "test_scheduled": "🧪 Vale, te mando un aviso de prueba dentro de {} segundos. Cierra Telegram o bloquea el móvil para ver cómo te llega.",
    "test_alert": "🧪 ESTO ES UNA PRUEBA, no hay plaza de verdad. Así te llegará el aviso:\n\n",
    "checking_time": "🔎 Compruebo en Renfe qué trenes salen ese día…",
    "time_found": "✅ Hay un tren a las {}. Vigilaré solo ese.",
    "time_not_found": "No sale ningún tren a las {}. Los más cercanos ese día son:\n{}\n\nPulsa la hora del que quieras vigilar.",
    "time_pick_invalid": "Elige una de las horas de los botones, o escribe la hora de un tren de ese día ({}).",
    "time_check_failed": "No he podido comprobar los horarios ahora mismo. Vigilaré el tren de las {} igualmente.",
    "no_trains_that_day": "Ese día no encuentro ningún tren entre esas estaciones. Escribe otra fecha, por ejemplo: 14/03/2027 09:30",
    "search_failing": "⚠️ Llevo 10 minutos sin poder consultar Renfe (sin internet o su web falla). Sigo intentándolo cada minuto.",
    "undefined_exception":"Oops, algo se ha roto y no sé el qué. Aquí va toda la traza: {}"
}


def get_tickets_message(trains: List[TrainRideRecord], origin: StationRecord, destination: StationRecord):
    message = (
        f"🚨 ¡Hay plaza! {origin.name.title()} → {destination.name.title()}, "
        f"{trains[0].departure_time:%d/%m/%Y}:\n\n"
    )
    for train in trains:
        message += str(train)
    message += "\nPulsa el botón para abrirlo en Renfe (marca «Solo ida» y busca). ¡Corre, que vuela!"
    return message
