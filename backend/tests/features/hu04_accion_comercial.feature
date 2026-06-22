# language: es
Característica: Realizar una acción comercial sobre un lead
  Como asesor
  Quiero registrar una acción comercial sobre un lead
  Para avanzar en el proceso de conversión y registrar observaciones sobre el cliente/lead

  Escenario: Registro de una acción comercial sobre un lead
    Dado un asesor autenticado en el módulo de leads
    Y una persona registrada con un lead activo
    Cuando registra una acción comercial de tipo "CALL_ATTEMPT" con la observación "Intento de contacto 1"
    Entonces el sistema responde con éxito y la acción queda registrada

  Escenario: Guardado de observación vinculada al lead
    Dado un asesor autenticado en el módulo de leads
    Y una persona registrada con un lead activo
    Cuando registra una acción comercial de tipo "NOTE" con la observación "Cliente interesado en plan premium"
    Entonces la observación queda guardada y vinculada al lead

  Escenario: Registro de la acción en el historial del lead
    Dado un asesor autenticado en el módulo de leads
    Y una persona registrada con un lead activo
    Cuando registra una acción comercial de tipo "NOTE" con la observación "Seguimiento"
    Entonces la acción aparece en el historial de actividades del lead
