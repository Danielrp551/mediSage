# language: es
Característica: Agregar citas sobre un cliente/lead existente (HU18)
  Como asesor
  Quiero registrar nuevas citas asociándolas a un cliente/lead ya existente
  Para registrar compromisos sin duplicar información y mantener el historial

  Escenario: Registro de una cita sobre un cliente/lead existente
    Dado un asesor autenticado con un escenario de agenda disponible
    Y un cliente registrado
    Cuando registra una nueva cita asociada al cliente existente
    Entonces el sistema responde con éxito y la cita queda asociada al cliente

  Escenario: Asociación de la cita al historial del lead
    Dado un asesor autenticado con un escenario de agenda disponible
    Y un cliente registrado
    Cuando registra una nueva cita asociada al cliente existente
    Entonces la cita queda registrada en el historial de citas del cliente

  Escenario: Validación de no duplicidad de citas en el mismo horario
    Dado un asesor autenticado con un escenario de agenda disponible
    Y un cliente registrado
    Y una cita ya registrada para el cliente en un horario
    Cuando intenta registrar otra cita para el mismo cliente en el mismo horario
    Entonces el sistema rechaza la cita por duplicidad de horario
