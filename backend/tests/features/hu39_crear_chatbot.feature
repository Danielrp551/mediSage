# language: es
Característica: Creación de un chatbot que maneje la atención al cliente y reservas de citas (HU39)
  Como administrador del sistema
  Quiero crear un chatbot asignándole nombre, tipo, descripción y una versión de comportamiento
  Para automatizar la comunicación y optimizar la gestión de agendamiento sin intervención manual

  Escenario: Creación de un chatbot con parámetros completos
    Dado un administrador del sistema autenticado en el módulo de chatbots
    Cuando crea un chatbot con nombre "Bot Recepción", tipo "general" y descripción "Atiende y agenda"
    Entonces el sistema permite crear el chatbot con los parámetros asignados

  Escenario: Vinculación del chatbot al sistema tras confirmar la creación
    Dado un administrador del sistema autenticado en el módulo de chatbots
    Y un chatbot creado con código "bot_clinica"
    Cuando el sistema confirma la creación
    Entonces el chatbot queda registrado y es recuperable en el sistema

  Escenario: Disponibilidad inmediata del chatbot para interacción
    Dado un administrador del sistema autenticado en el módulo de chatbots
    Y un chatbot creado con código "bot_disponible"
    Cuando el chatbot queda registrado en el sistema
    Entonces el chatbot está disponible de inmediato en el listado de bots activos

  Escenario: El chatbot queda operativo al asignarle una versión vigente
    Dado un administrador del sistema autenticado en el módulo de chatbots
    Y un chatbot creado con código "bot_operativo"
    Cuando le crea una versión de comportamiento con un prompt
    Entonces el chatbot tiene una versión vigente y queda operativo
