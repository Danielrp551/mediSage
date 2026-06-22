# language: es
Característica: Visualizar y gestionar chats de clientes/leads (HU19)
  Como asesor o administrador de clínica
  Quiero visualizar la lista de chats en curso tomados por asesores
  Para supervisar las conversaciones y dar seguimiento al estado de cada interacción

  Escenario: Visualización de la lista de chats tomados por asesores
    Dado un asesor autenticado en el módulo de chats
    Y una cuenta de canal de WhatsApp registrada
    Y un chat entrante de un contacto que es tomado por el asesor
    Cuando accede a la vista de chats en curso
    Entonces el sistema muestra la lista de chats indicando cliente/lead y asesor responsable

  Escenario: Orden de chats por fecha y hora de la última interacción
    Dado un asesor autenticado en el módulo de chats
    Y una cuenta de canal de WhatsApp registrada
    Y dos chats entrantes de contactos distintos en distinto momento
    Cuando accede a la vista de chats en curso
    Entonces los chats están ordenados por fecha y hora de la última interacción

  Escenario: Visualización del estado actual de cada chat
    Dado un asesor autenticado en el módulo de chats
    Y una cuenta de canal de WhatsApp registrada
    Y un chat entrante de un contacto
    Cuando accede a la vista de chats en curso
    Entonces se muestra el estado actual de cada chat
