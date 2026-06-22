# language: es
Característica: Visualizar los leads y aplicar filtros de búsqueda (HU01)
  Como asesor
  Quiero visualizar la lista de personas (leads) y aplicar filtros
  Para gestionar los prospectos de forma eficiente

  Escenario: Visualización completa de la lista de leads
    Dado un asesor autenticado
    Y una persona registrada con nombre "Ana"
    Cuando solicita la lista de personas
    Entonces el sistema responde con éxito y la lista incluye la persona

  Escenario: Aplicación de un filtro de búsqueda por nombre
    Dado un asesor autenticado
    Y una persona registrada con nombre "Ana"
    Cuando solicita la lista de personas filtrando el nombre por "Ana"
    Entonces el sistema responde con éxito y todos los resultados coinciden con el filtro
