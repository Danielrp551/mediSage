# language: es
Característica: Configurar servicios que brinda una clínica (HU28)
  Como administrador de clínica
  Quiero registrar, actualizar y eliminar servicios asociados a una vertical
  Para mantener actualizado el portafolio de atención

  Escenario: Gestión de servicios de la clínica
    Dado un administrador de clínica autenticado
    Y una vertical registrada con código "dermatologia"
    Cuando registra un servicio "limpieza_facial" con nombre "Limpieza facial"
    Entonces el sistema confirma el registro del servicio
    Cuando actualiza el nombre del servicio a "Limpieza Premium"
    Entonces el sistema confirma la actualización del servicio
    Cuando elimina el servicio
    Entonces el sistema confirma la eliminación del servicio

  Escenario: Asociación del servicio a una vertical con descripción
    Dado un administrador de clínica autenticado
    Y una vertical registrada con código "odontologia"
    Cuando registra un servicio "ortodoncia" con descripción "Tratamiento de ortodoncia"
    Entonces el servicio queda asociado a la vertical y tiene la descripción registrada

  Escenario: Reflejo inmediato de los cambios en los canales de atención
    Dado un administrador de clínica autenticado
    Y una vertical registrada con código "estetica"
    Y un servicio "masaje_relax" registrado en la vertical
    Cuando consulta los servicios activos de la vertical
    Entonces el servicio aparece de inmediato en la lista de servicios activos
