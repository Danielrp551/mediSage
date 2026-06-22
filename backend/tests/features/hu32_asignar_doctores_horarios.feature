# language: es
Característica: Asignar doctores a horarios (HU32)
  Como administrador de clínica
  Quiero asignar doctores a horarios en sedes y consultorios específicos
  Para garantizar la distribución de la carga laboral y la disponibilidad médica

  Escenario: Asignación de un doctor a un horario específico
    Dado un administrador de clínica autenticado
    Y una sede con un consultorio registrados
    Y un doctor asignado a esa sede
    Cuando asigna al doctor un horario "08:00:00" a "13:00:00" en esa sede y consultorio
    Entonces el sistema registra la asignación de disponibilidad del doctor

  Escenario: Validación de la disponibilidad del doctor en la asignación
    Dado un administrador de clínica autenticado
    Y una sede con un consultorio registrados
    Y un doctor asignado a esa sede
    Y el doctor ya tiene un horario "08:00:00" a "13:00:00" en esa sede y consultorio
    Cuando asigna al doctor un horario "12:00:00" a "18:00:00" en esa sede y consultorio
    Entonces el sistema rechaza la asignación por solapamiento de disponibilidad
