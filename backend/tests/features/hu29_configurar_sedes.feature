# language: es
Característica: Configurar sedes que tiene una clínica (HU29)
  Como administrador de clínica
  Quiero registrar, editar y eliminar las sedes de la clínica
  Para gestionar de forma organizada los diferentes puntos de atención

  Escenario: Gestión de sedes de la clínica
    Dado un administrador de clínica autenticado en el módulo Mi Clínica
    Cuando registra una sede con código "sede_central"
    Entonces el sistema permite registrar la sede correctamente
    Y al editar el nombre de la sede el cambio se guarda
    Y al eliminar la sede ya no se encuentra disponible

  Escenario: Registro de datos básicos de cada sede
    Dado un administrador de clínica autenticado en el módulo Mi Clínica
    Cuando registra una sede con dirección, contacto y descripción
    Entonces la sede registrada incluye dirección y datos de contacto

  Escenario: Reflejo de cambios en el portafolio
    Dado un administrador de clínica autenticado en el módulo Mi Clínica
    Y una sede registrada con código "sede_portafolio"
    Cuando consulta las sedes activas
    Entonces la sede aparece en el listado de sedes activas
