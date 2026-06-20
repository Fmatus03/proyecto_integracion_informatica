# Especificacion del Informe Final

## Proyecto ForestVol

### Objetivo

Documentar de forma completa, tecnica y trazable el desarrollo, validacion y resultados del proyecto ForestVol.

### Fuente de verdad tecnica

La base tecnica del informe debe salir de:

- `projects/ForestVol/FORESTVOL_MVP_SPEC.md`
- artefactos reales del proyecto
- trazabilidad del harness
- resultados efectivamente obtenidos

El informe no debe inventar componentes, modulos, arquitecturas o resultados fuera de esa base.

### Restricciones de contenido

- No presentar ForestVol como solucion IoT, LoRaWAN, AWS, app movil o sistema basado en sensores remotos.
- No incluir base de datos relacional, machine learning o servicios cloud como parte del MVP si no fueron implementados.
- No afirmar cumplimiento de RF-09 sin Ground Truth certificado.
- Diferenciar con claridad entre implementado, validado, pendiente y trabajo futuro.

---

# Capitulo 1. Introduccion

Debe incluir:

- problema
- justificacion
- objetivo general
- objetivos especificos
- alcance
- restricciones

El problema debe centrarse en la estimacion del volumen de acopios de madera mediante imagenes RGB y fotogrametria 3D.

---

# Capitulo 2. Antecedentes generales

## 2.1 Estado del arte

Cubrir solo temas pertinentes a ForestVol:

- fotogrametria 3D
- SfM y MVS
- marcadores ArUco y calibracion espacial
- reconstruccion de nubes de puntos y mallas
- calculo de volumen en mallas cerradas
- visualizacion 3D web

## 2.2 Fundamentos teoricos

Explicar con suficiente profundidad:

- flujo de reconstruccion fotogrametrica
- relacion entre escala fisica y medicion digital
- necesidad de mallas watertight para volumen
- significado de Ground Truth y error porcentual

## 2.3 Comparacion de alternativas

Justificar las decisiones reales del proyecto, por ejemplo:

- NodeODM como motor fotogrametrico
- OpenCV para calibracion con ArUco
- Open3D para malla y volumen
- Vue y Three.js para interfaz y visualizacion

---

# Capitulo 3. Metodologia y desarrollo

## 3.1 Metodologia aplicada

Describir como se ejecuto el trabajo por hitos y etapas, usando trazabilidad real y Definition of Done.

## 3.2 Requisitos

Debe incluir:

- requisitos funcionales relevantes del MVP
- requisitos no funcionales relevantes del MVP

## 3.3 Arquitectura

Incluir diagramas y explicaciones de:

- servicios Docker Compose
- backend FastAPI
- frontend Vue
- NodeODM
- flujo de datos del pipeline

No incluir arquitectura cloud si no forma parte del sistema real.

## 3.4 Diseno tecnico

Describir:

- endpoints principales
- estados del pipeline
- servicios clave del backend
- artefactos generados
- estructura de datos de resultados y exportaciones

## 3.5 Implementacion

Debe describir unicamente lo que pertenece a ForestVol:

- carga y validacion de imagenes
- calibracion con ArUco
- reconstruccion SfM/MVS
- generacion y reparacion de malla
- calculo volumetrico
- visualizacion 3D
- exportacion JSON y CSV

## 3.6 Reproducibilidad

Debe incluir:

- repositorio
- estructura del proyecto
- dependencias
- versiones
- instrucciones de despliegue y pruebas

---

# Capitulo 4. Resultados y discusion

## 4.1 Producto funcional

Mostrar evidencia real, por ejemplo:

- capturas de interfaz
- resultados del pipeline
- ejemplos de artefactos exportados
- evidencia de visualizacion 3D

## 4.2 Validacion

Debe cubrir, cuando exista evidencia:

- pruebas funcionales
- pruebas de integracion
- pruebas end to end
- cumplimiento de requisitos
- estado de cobertura
- validacion de malla
- validacion de volumen

## 4.3 Trazabilidad

Incluir tabla del tipo:

Objetivo o requisito -> evidencia -> resultado -> estado

## 4.4 Discusion tecnica

Analizar:

- fortalezas del enfoque
- limitaciones del dataset
- dependencia de la calidad de imagenes
- restricciones de operacion local y CPU only
- impacto de no contar aun con Ground Truth certificado, si aplica

## 4.5 Limitaciones y amenazas a la validez

Distinguir claramente:

- limitaciones del MVP
- limitaciones del dataset
- limitaciones del entorno de prueba
- riesgos metodologicos

---

# Capitulo 5. Conclusiones

Cada conclusion debe relacionarse explicitamente con:

- problema
- objetivos
- resultados observados

No redactar conclusiones que excedan la evidencia real del proyecto.

---

# Trabajo futuro

Solo incluir mejoras coherentes con ForestVol, por ejemplo:

- ampliar dataset
- certificar Ground Truth
- mejorar robustez de reconstruccion
- optimizar tiempos de procesamiento
- mejorar experiencia de usuario del frontend

---

# Bibliografia

Usar formato institucional UFRO y priorizar:

- papers academicos relevantes
- documentacion oficial de las tecnologias usadas
- referencias tecnicas del dominio fotogrametrico

---

# Anexos

Opcionales, pero recomendados:

- tablas de pruebas
- casos de prueba
- diagramas completos
- ejemplos de exportaciones
- capturas del pipeline
- manual tecnico o de uso

---

# Requisitos minimos para evaluacion sobresaliente

Debe evidenciar:

- coherencia total con `FORESTVOL_MVP_SPEC.md`
- arquitectura y diagramas propios del sistema real
- trazabilidad entre objetivos, requisitos, implementacion y evidencia
- diferenciacion clara entre logrado, parcial y pendiente
- validacion objetiva sin inflar resultados
- autoria tecnica visible en decisiones, implementacion y analisis
