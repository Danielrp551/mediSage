# language: es
Característica: Registrar una nueva campaña (HU24)
  Como asesor o administrador de clínica
  Quiero registrar una nueva campaña en el módulo de campañas
  Para implementar acciones de marketing orientadas a captar o fidelizar pacientes

  Escenario: Registro de una nueva campaña con datos completos
    Dado un asesor autenticado en el módulo de campañas
    Cuando registra una nueva campaña con nombre "Verano Saludable", descripción y fechas de inicio/fin
    Entonces el sistema debe permitir registrar la campaña con sus datos completos

  Escenario: Asociación de la campaña al historial de campañas de la clínica
    Dado un asesor autenticado en el módulo de campañas
    Y ha registrado una nueva campaña con nombre "Campaña Fidelización"
    Cuando consulta el historial de campañas
    Entonces la campaña registrada debe figurar en el historial de campañas

  Escenario: Validación de unicidad de campaña por código
    Dado un asesor autenticado en el módulo de campañas
    Y ya existe una campaña con un código determinado
    Cuando intenta registrar otra campaña con el mismo código
    Entonces el sistema debe rechazar el registro por código duplicado
