# Especificacion del Anteproyecto

## Proyecto ForestVol

### Objetivo

Definir formalmente el problema, la solucion propuesta, la metodologia de trabajo y la planificacion del proyecto ForestVol antes de su desarrollo completo.

### Fuente de verdad tecnica

Este documento no redefine el producto. La fuente de verdad tecnica para arquitectura, stack, alcance, restricciones e hitos del sistema es:

- `projects/ForestVol/FORESTVOL_MVP_SPEC.md`

El anteproyecto debe usar esa especificacion como base y no inventar componentes fuera del MVP.

### Restricciones de contenido

- No describir ForestVol como plataforma IoT, LoRaWAN, AWS o aplicacion movil.
- No agregar sensores, nube, base de datos relacional, LiDAR, GPS obligatorio ni machine learning si no aparecen en la spec del MVP.
- No prometer metricas finales que aun no tengan evidencia.
- Si no existe Ground Truth certificado, dejar explicito que RF-09 no puede darse por cumplido.

---

# 1. Portada

Debe seguir el formato institucional UFRO e incluir como minimo:

- Universidad
- Facultad o departamento
- Titulo del proyecto
- Modalidad de titulacion
- Nombre del estudiante
- Profesor guia
- Fecha o ano

---

# 2. Introduccion

## 2.1 Contexto

Describir el problema operativo de estimar volumen de acopios de madera de forma manual o poco reproducible, y la necesidad de automatizar esa tarea con fotogrametria 3D.

## 2.2 Problema

Definir con claridad:

- que problema ocurre en la medicion de castillos de madera
- a quien afecta
- por que afecta decisiones operativas o tecnicas
- que limitaciones tienen los metodos manuales o no estandarizados

## 2.3 Justificacion

Explicar el valor del proyecto desde estas dimensiones:

- valor tecnico
- valor operativo
- valor academico
- valor de reproducibilidad y trazabilidad

## 2.4 Objetivo general

Un unico objetivo medible, coherente con la hipotesis del MVP: estimar volumen de acopios de madera a partir de imagenes RGB mediante un pipeline reproducible.

## 2.5 Objetivos especificos

Entre 4 y 8 objetivos verificables. Deben cubrir, segun corresponda:

- validacion de imagenes de entrada
- calibracion espacial con marcador ArUco
- reconstruccion 3D con NodeODM
- generacion de malla cerrada
- calculo volumetrico en m3
- visualizacion y exportacion de resultados
- validacion contra Ground Truth cuando exista

---

# 3. Antecedentes generales

## 3.1 Estado del arte

Debe centrarse en temas realmente pertinentes a ForestVol:

- fotogrametria 3D aplicada a volumetria
- reconstruccion SfM y MVS
- calibracion con referencias fisicas y marcadores ArUco
- procesamiento de nubes de puntos y mallas
- estimacion de volumen sobre mallas cerradas
- visualizacion 3D web

## 3.2 Comparacion de alternativas

Comparar alternativas reales del proyecto, por ejemplo:

- OpenDroneMap o NodeODM frente a otras opciones de reconstruccion
- ArUco frente a otros metodos de escala
- Open3D frente a otras librerias de procesamiento 3D
- GLB, PLY y OBJ segun su rol en el pipeline

Toda decision debe justificarse con relacion a costo, reproducibilidad, operacion local y alcance MVP.

---

# 4. Metodologia

## 4.1 Metodologia de desarrollo

Describir una metodologia compatible con el proyecto y con la trazabilidad por hitos. Puede ser incremental o iterativa, siempre alineada con los hitos definidos en la spec del MVP.

## 4.2 Etapas

Usar como base las fases reales de ForestVol:

- infraestructura base
- carga y validacion de imagenes
- integracion con NodeODM
- calibracion espacial
- malla 3D y volumetria preliminar
- volumetria funcional y exportacion
- frontend
- estabilizacion y cierre

## 4.3 Productos por etapa

Debe existir trazabilidad entre:

Etapa -> Entregable -> Evidencia esperada

---

# 5. Programa de trabajo

Debe incluir una carta Gantt o plan equivalente con:

- actividades
- duracion
- dependencias
- hitos
- entregables

Los hitos deben ser consistentes con:

- Hito 0: validacion tecnica
- Hito 1: calibracion espacial
- Hito 0.5: volumetria preliminar
- Hito 2: volumetria funcional
- Hito 3: MVP completo

---

# 6. Recursos y costos

Presentar costos y recursos realmente asociados al MVP. Considerar, segun aplique:

- hardware de referencia
- almacenamiento local
- impresiones o fabricacion de la guia ArUco
- tiempo de desarrollo
- infraestructura Docker local

No incluir costos de nube, LoRaWAN, sensores o app movil salvo que se explicite que quedan fuera del alcance actual.

---

# 7. Validacion propuesta

Debe explicar como se evaluara el proyecto:

- validacion funcional del pipeline
- pruebas unitarias, integracion y e2e
- validacion de malla cerrada
- validacion de volumen estimado
- uso de Ground Truth certificado cuando este disponible

Si aun no existe Ground Truth certificado, dejar explicito que la medicion del error volumetrico queda pendiente.

---

# 8. Bibliografia

Usar fuentes academicas y tecnicas pertinentes, preferentemente:

- papers de fotogrametria y reconstruccion 3D
- documentacion oficial de OpenCV, OpenDroneMap o NodeODM, Open3D, FastAPI y Vue
- estandares o referencias metodologicas relevantes

---

# Criterio de aceptacion

El anteproyecto debe permitir comprender con claridad:

- que problema resuelve ForestVol
- por que la fotogrametria 3D es una solucion razonable
- como se construira el sistema dentro del alcance del MVP
- como se organizan etapas, hitos y entregables
- como se validara el sistema sin afirmar resultados no demostrados
