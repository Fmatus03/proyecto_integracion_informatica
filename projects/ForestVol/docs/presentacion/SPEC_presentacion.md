# Especificacion Presentacion Final

## Proyecto ForestVol

### Objetivo

Defender tecnicamente el proyecto ForestVol mostrando con claridad el problema, la solucion, la implementacion real y los resultados efectivamente obtenidos.

### Fuente de verdad tecnica

La presentacion debe alinearse con:

- `projects/ForestVol/FORESTVOL_MVP_SPEC.md`
- implementacion real del proyecto
- trazabilidad y evidencia disponible

No debe inventar modulos, arquitectura ni resultados fuera del MVP.

### Restricciones de contenido

- No mostrar ForestVol como plataforma IoT, LoRaWAN, AWS ni app movil.
- No usar diagramas de sensores o nube si no pertenecen al sistema real.
- No afirmar precision final ni cumplimiento de RF-09 sin evidencia y Ground Truth certificado.
- Cada afirmacion importante debe estar respaldada por evidencia visual, tecnica o trazable.

---

# Diapositiva 1

Portada

- titulo del proyecto
- estudiante
- profesor guia
- universidad
- fecha

---

# Diapositiva 2

Problema

Responder:

- que problema existe en la estimacion del volumen de acopios de madera
- por que el proceso manual o no estandarizado es insuficiente
- que impacto tiene el problema

---

# Diapositiva 3

Objetivos

- objetivo general
- objetivos especificos principales

Deben ser consistentes con la hipotesis y el alcance del MVP.

---

# Diapositiva 4

Propuesta de solucion

Vista general de ForestVol:

- entrada de imagenes RGB
- calibracion espacial con ArUco
- reconstruccion 3D
- malla
- calculo de volumen
- visualizacion y exportacion

---

# Diapositiva 5

Arquitectura

Mostrar el sistema real, por ejemplo:

Operador -> Frontend Vue -> API FastAPI -> NodeODM / OpenCV / Open3D -> resultados y exportaciones

Puede incluir diagrama de servicios Docker Compose.

---

# Diapositiva 6

Metodologia y plan

Mostrar:

- hitos principales
- etapas del desarrollo
- entregables relevantes
- trazabilidad resumida

---

# Diapositiva 7

Implementacion

Mostrar componentes reales:

- backend
- frontend
- integracion con NodeODM
- calibracion con ArUco
- generacion de malla y volumen

---

# Diapositiva 8

Resultados

Demostrar funcionamiento con evidencia real:

- capturas de interfaz
- visualizacion 3D
- exportaciones
- estados del pipeline

---

# Diapositiva 9

Validacion

Mostrar:

- pruebas ejecutadas
- requisitos cubiertos
- metricas disponibles
- estado de Ground Truth
- limitaciones de la validacion, si existen

---

# Diapositiva 10

Conclusiones

- logros principales
- aprendizajes tecnicos
- limitaciones reales del MVP

---

# Diapositiva 11

Trabajo futuro

Solo mejoras coherentes con ForestVol, por ejemplo:

- ampliar dataset
- mejorar calibracion
- certificar Ground Truth
- optimizar rendimiento
- robustecer frontend o pipeline

---

# Diapositiva 12

Preguntas

Diapositiva de cierre.

---

# Reglas

- maximo 12 diapositivas
- poco texto por slide
- priorizar diagramas propios del sistema real
- priorizar evidencia visual autentica
- no incluir tecnologias fuera del alcance del MVP
- cada objetivo debe vincularse con evidencia o estado verificable
