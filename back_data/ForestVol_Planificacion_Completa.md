  
**ForestVol v5.1**

Sistema de Cálculo Volumétrico de Castillos de Madera

*Planificación Integral del Proyecto*

MVP Scrum — Fabián Matus Alarcón

| Autor | Fabián Matus Alarcón |
| :---: | :---- |
| **Versión** | 5.1 — Consolidada Profesional |
| **Metodología** | Scrum Adaptado — Desarrollador Único |
| **Duración MVP** | 5 Semanas · 125 horas de capacidad |
| **Inicio MVP** | 3 de junio de 2025 |
| **Entrega Final** | 6 de julio de 2025 |

# **1\. Problemática Central**

*Entregado: 27 de marzo de 2025*

## **1.1 Planteamiento del Problema**

Actualmente, en la industria forestal y la gestión de acopios, los supervisores de terreno e ingenieros forestales enfrentan la necesidad de medir manual o visualmente el volumen de los castillos de troncos, lo que provoca imprecisiones en el inventario, grandes pérdidas de tiempo y exposición del personal a riesgos físicos. Esta situación dificulta el control de stock, la logística de transporte y la valoración económica de la madera, por lo que resulta pertinente desarrollar una solución que permita automatizar y calcular con alta precisión el volumen maderero mediante fotogrametría con drones, mejorando así la toma de decisiones.

## **1.2 Contexto y Justificación**

En el sector forestal, cuantificar el volumen de los castillos de madera tradicionalmente requiere inspecciones manuales o estimaciones visuales, métodos que resultan lentos, imprecisos y riesgosos para el personal. Este proyecto se justifica por la necesidad de modernizar el control de inventario mediante la integración de nuevas tecnologías.

Al utilizar drones para capturar imágenes y aplicar fotogrametría tridimensional, se podrá calcular el volumen exacto de los acopios de forma remota y eficiente. Esto reducirá drásticamente los costos operativos y tiempos de medición, mejorará la planificación logística y alejará a los trabajadores de terrenos irregulares o peligrosos, aportando un gran valor a la industria.

## **1.3 Dominios Técnicos del Proyecto**

*Entregado: 17 de abril de 2025*

| Dominio | Área | Justificación |
| ----- | ----- | ----- |
| **Principal** | Ingeniería de Datos | Núcleo técnico para resolver la imprecisión volumétrica mediante procesamiento de información espacial obtenida a través de drones. |
| **Complementario** | Visualización de Datos | Interfaz clara para la lectura de resultados del modelado 3D y métricas en terreno, mejorando la integración operativa. |
| **Remedial** | Inteligencia Artificial | Exploración de algoritmos de visión computacional para automatizar y mejorar la detección y segmentación en capturas fotográficas. |

# **2\. Estado del Arte**

*Entregado: 24 de abril de 2025*

## **2.1 Introducción y Contexto Científico**

La cuantificación precisa del volumen de madera apilada es un proceso crítico en la cadena de suministro, comercialización forestal y la planificación de la logística de transporte. La literatura científica reciente (2023–2025) evidencia una transición acelerada hacia el uso de tecnologías de teledetección (Remote Sensing), fotogrametría digital e Inteligencia Artificial.

## **2.2 Hallazgos Científicos Clave**

### **Sensores RGB Estándar (Ucar et al., 2024\)**

El estudio evaluó sensores ópticos comerciales para medir acopios de madera en 21 pilas de troncos. Los autores encontraron fuerte correlación entre el volumen estimado y el medido manualmente, validando que las cámaras RGB estándar (drones comerciales) son dispositivos de entrada completamente válidos. Esto permite diseñar arquitecturas de software de bajo costo operativo.

### **Calibración Métrica vs. LiDAR (Purfürst et al., 2023\)**

Comparativa entre nueve métodos de medición en 47 acopios demostró que los métodos fotogramétricos logran precisiones volumétricas comparables a sistemas LiDAR, sin necesidad de sensores de tiempo de vuelo. Justificación empírica del uso de una guía física de 50×50 cm para escalar los modelos.

### **Irrelevancia de GCPs (Araújo Júnior et al., 2025\)**

Evaluación sobre 24 pilas de madera de Eucalyptus sp. demostró que las estimaciones de volumen son estadísticamente similares con o sin Puntos de Control Terrestre (GCPs). Esto valida que el motor fotogramétrico puede calcular volumen basándose únicamente en métricas relativas, haciendo innecesario el uso de drones con RTK.

### **YOLOv8 para Volumen Sólido (Goycochea Casas et al., 2024\)**

Propone modelo integral con redes neuronales convolucionales (YOLOv8) para segmentación de instancias de troncos. La metodología post-segmentación aplica modelos estadísticos de distribución de diámetros para calcular el volumen sólido total con precisión comparable a la medición destructiva.

## **2.3 Stack Tecnológico — Selección Multicriterio**

| Categoría | Seleccionado | Puntaje | Alternativas |
| ----- | ----- | ----- | ----- |
| Motor Fotogramétrico | OpenDroneMap / NodeODM | 4.80/5.00 | Meshroom, MicMac |
| Procesamiento Geométrico | Open3D | 4.85/5.00 | CloudCompare, PDAL |
| Detección/Segmentación IA | YOLOv8 (Ultralytics) | 4.80/5.00 | OpenCV clásico |
| Lenguaje de Orquestación | Python 3.x | 4.80/5.00 | C++ |
| Frontend / Visualización | Vue.js \+ Three.js (SPA) | 4.80/5.00 | Streamlit, PyQt |
| Infraestructura | Docker \+ Docker Compose | — | Bare metal |

# **3\. Objetivos y Alcance**

*Entregado: 10 de abril de 2025*

## **3.1 Objetivo General**

Desarrollar un sistema de software basado en fotogrametría mediante el uso de drones para el cálculo volumétrico de castillos de madera, utilizando capturas aéreas reales a escala controlada para mejorar la precisión y seguridad del inventario forestal.

## **3.2 Objetivos Específicos**

1. Investigar las soluciones de fotogrametría y procesamiento de imágenes disponibles en la actualidad, entregando un Cuadro Comparativo de Viabilidad Técnica que defina el stack tecnológico final a utilizar según los requerimientos de precisión y costo del proyecto.

2. Capturar y parametrizar un set de imágenes fotogramétricas aéreas en terreno mediante vuelos de dron, utilizando referencias métricas físicas directas para asegurar la calibración espacial del modelo.

3. Implementar el flujo de procesamiento de las imágenes capturadas para generar modelos tridimensionales y automatizar algorítmicamente el cálculo del volumen del acopio.

4. Contrastar el cálculo volumétrico del software con mediciones físicas en terreno para determinar el margen de error del sistema, entregando una Matriz de Comparación y Ajuste de Precisión.

## **3.3 Alcance del Proyecto**

El proyecto desarrollará un sistema de procesamiento fotogramétrico integral que utiliza la captura de imágenes mediante drones para calcular el volumen de castillos de madera, abordando de manera definitiva el problema de la imprecisión, lentitud y riesgo del control manual de inventarios forestales.

### **Exclusiones Explícitas**

* Identificación automatizada de especies madereras

* Integración directa o mediante APIs con plataformas ERP corporativas

* Uso de LiDAR, drones con RTK, o GCPs absolutos en terreno

* Módulos de inteligencia artificial de alta complejidad (YOLOv8) en el MVP

* Dashboards avanzados, Three.js avanzado, multiusuario

## **3.4 Hipótesis del MVP**

| *Es posible calcular automáticamente el volumen aproximado de un castillo de madera utilizando únicamente imágenes fotogramétricas RGB, sin requerir sensores LiDAR ni coordenadas GPS absolutas, obteniendo un error máximo del 15%.* |
| :---- |

# **4\. Método — Pipeline Técnico**

El pipeline de ForestVol está estructurado en 7 etapas secuenciales, con dependencias explícitas entre módulos. Cada etapa produce un artefacto concreto y medible que sirve de insumo para la siguiente.

## **4.1 Diagrama de Etapas y Productos**

| \# | Etapa | Descripción | Producto Principal | Módulo |
| ----- | ----- | ----- | ----- | ----- |
| **1** | Captura Fotográfica | Vuelo de dron con cámara RGB estándar sobre el castillo de madera. La guía de calibración (50×50 cm) debe estar visible en el acopio. | Set de imágenes JPG/PNG (≥20 imágenes, ≥24 MP) | Operación en Terreno |
| **2** | Carga y Validación | Ingesta del set de imágenes en la interfaz web. El sistema valida formato (JPG/PNG) y rechaza archivos inválidos en \<2 seg. | Imágenes disponibles en el sistema sin errores | RF-01, RF-02 |
| **3** | Calibración Espacial | OpenCV detecta automáticamente los contornos de la guía 50×50 cm. Calcula la relación px/cm y genera la matriz de transformación. Si no detecta guía, alerta al operador. | Escala métrica aplicada al modelo. Error de escala ≤5%. | RF-03, RF-04, RF-05 |
| **4** | Reconstrucción Fotogramétrica SfM/MVS | NodeODM ejecuta Structure from Motion (SfM) y Multi-View Stereo (MVS) sobre las imágenes calibradas para reconstruir la geometría 3D del castillo. | Nube de puntos densa (cobertura ≥90% del castillo) | RF-06 |
| **5** | Generación de Malla 3D | A partir de la nube de puntos, Open3D construye una malla tridimensional cerrada (watertight mesh). Si la malla presenta errores, se ejecuta reparación automática. | Malla 3D cerrada, apta para volumetría (agujeros \<5%) | RF-07 |
| **6** | Cálculo Volumétrico | Open3D verifica integridad de la malla y ejecuta el algoritmo de cálculo volumétrico sobre la malla escalada. Resultado expresado en m³. | Volumen aparente en m³. Error ≤15% vs. Ground Truth. | RF-08, RF-09 |
| **7** | Visualización y Exportación | Three.js renderiza el modelo 3D en la interfaz Vue.js. El operador visualiza métricas (volumen, escala, n° imágenes). Exportación JSON/CSV disponible. | Panel web con métricas. Archivos JSON/CSV descargables. | RF-10, RF-11, RF-12 |

## **4.2 Flujo del Pipeline (Descripción Textual)**

El siguiente flujo describe la secuencia de transformaciones de datos a lo largo del pipeline:

| Imágenes JPG/PNG     ↓  \[RF-01, RF-02\] Validación de formato y carga Set de imágenes validadas     ↓  \[RF-03, RF-04, RF-05\] Detección guía \+ calibración espacial (OpenCV) Imágenes con escala métrica aplicada     ↓  \[RF-06\] SfM \+ MVS (NodeODM via Docker) Nube de puntos densa (.LAS / .PLY)     ↓  \[RF-07\] Construcción y reparación de malla 3D (Open3D) Malla 3D cerrada (.OBJ / .PLY)     ↓  \[RF-08, RF-09\] Cálculo volumétrico (Open3D) Volumen en m³ \+ Metadatos     ↓  \[RF-10, RF-11, RF-12\] Visualización 3D (Three.js) \+ Exportación (JSON/CSV) |
| :---- |

# **5\. Implementación del Sistema**

## **5.1 Recursos e Insumos del Proyecto**

### **Recursos de Software (Stack Técnico)**

| Componente | Tecnología | Rol en el Sistema |
| ----- | ----- | ----- |
| Motor Fotogramétrico | OpenDroneMap / NodeODM | Reconstrucción SfM/MVS. API REST. Desplegado en Docker. |
| Detección de Guía | OpenCV (Python) | Detección de contornos, calibración espacial, escalado métrico. |
| Procesamiento Geométrico | Open3D (Python) | Construcción y reparación de malla 3D. Cálculo volumétrico. |
| Backend API | Python 3.x \+ FastAPI | Orquestación del pipeline. Endpoints REST para el frontend. |
| Frontend SPA | Vue.js \+ Three.js | Interfaz web. Visualización 3D interactiva. Exportación de reportes. |
| Infraestructura | Docker \+ Docker Compose | Contenerización de todos los servicios. Reproducibilidad. |

### **Recursos de Hardware**

| Recurso | Especificación |
| ----- | ----- |
| Equipo de Desarrollo | Hardware académico convencional (CPU). Sin requisito de GPU con CUDA. |
| Dataset | Simulado: mínimo 10 imágenes fotogramétricas, validación contra Ground Truth. |
| Guía de Calibración | Marco físico de 50×50 cm dispuesto en el acopio durante la captura. |
| Conectividad | Local. Sin dependencia de internet para el procesamiento (RNF-08). |

## **5.2 Entregables del Proyecto**

| Entregable | Descripción | Fecha | Criterio de Éxito |
| ----- | ----- | ----- | ----- |
| Problemática Central | Planteamiento del problema y justificación | 27 mar. 2025 | Entregado ✓ |
| Objetivos y Alcance | OG, OE y delimitación del sistema | 10 abr. 2025 | Entregado ✓ |
| Dominios Técnicos | Ingeniería de Datos, Visualización, IA | 17 abr. 2025 | Entregado ✓ |
| Estado del Arte | Literatura científica y selección tecnológica | 24 abr. 2025 | Entregado ✓ |
| Requisitos y Casos de Uso | RF/RNF y diagrama de actividades/estado | 23 may. 2025 | Entregado ✓ |
| Diagramas de Arquitectura | Vistas lógica, procesos, desarrollo, física y escenarios | 29 may. 2025 | Entregado ✓ |
| Planificación MVP (Este Doc.) | Método, implementación, carta Gantt | 2 jun. 2025 | Presente ✓ |
| MVP Funcional | Sistema ejecutable con error ≤15% | 6 jul. 2025 | Error volumétrico ≤15% |
| Informe Final | Documentación técnica y científica completa del proyecto | 6 jul. 2025 | Todos los criterios cumplidos |
| Video Demostrativo | Demo funcional del sistema completo en operación | 6 jul. 2025 | Pipeline completo ejecutado |

## **5.3 Resultados Evaluables y Medibles**

| Métrica | Valor Objetivo | Método de Verificación |
| ----- | ----- | ----- |
| Error volumétrico (Hito 2\) | ≤ 15% vs. Ground Truth | Fórmula: |V\_sistema − V\_GT| / V\_GT × 100 |
| Error volumétrico preliminar (Hito 0.5) | ≤ 25% | Cálculo volumétrico sobre malla en Sprint 3 |
| Detección de guía de calibración | ≥ 90% en imágenes donde es visible | Comparación automático vs. confirmación manual |
| Error de escala métrica | ≤ 5% (guía de 50 cm) | Medición del lado de la guía en el modelo 3D |
| Cobertura de nube de puntos | ≥ 90% del castillo | Inspección con Open3D |
| Malla 3D cerrada | Agujeros \< 5% de la superficie | Análisis watertightness con Open3D |
| Tiempo de procesamiento | \< 30 min por dataset completo | Medición en hardware académico |
| Carga de imágenes simultáneas | ≥ 20 imágenes JPG/PNG hasta 24 MP | Prueba funcional: 20+ imágenes reales |
| Cumplimiento Sprint Goal | 100% por sprint | Revisión en Sprint Review de cada iteración |

**6\. Planificación — Carta Gantt**

## **6.1 Cronograma General del Proyecto**

| Entregable / Hito | Período | Fecha | Descripción |
| ----- | ----- | ----- | ----- |
| Problemática Central | Sem. 1 (mar.) | 27 mar. 2025 | Planteamiento del problema ✓ |
| Objetivos \+ Alcance | Sem. 2 (abr.) | 10 abr. 2025 | OG, OE y delimitación ✓ |
| Dominios Técnicos | Sem. 3 (abr.) | 17 abr. 2025 | Dominios del proyecto ✓ |
| Estado del Arte | Sem. 4 (abr.) | 24 abr. 2025 | Literatura y stack tecnológico ✓ |
| Requisitos \+ Casos de Uso | Sem. 8 (may.) | 23 may. 2025 | RF/RNF, UC, diagramas ✓ |
| Diagramas de Arquitectura | Sem. 9 (may.) | 29 may. 2025 | 5 vistas arquitecturales ✓ |
| Planificación MVP (Hoy) | Sem. 10 (jun.) | 2 jun. 2025 | Este documento ✓ |
| Sprint 1 — MVP Inicio | Semana 1 MVP | 3–9 jun. 2025 | Validación técnica inicial (Hito 0\) |
| Sprint 2 — Calibración | Semana 2 MVP | 10–16 jun. 2025 | Calibración espacial funcional (Hito 1\) |
| Sprint 3 — Geometría 3D | Semana 3 MVP | 17–23 jun. 2025 | Malla apta para volumetría \+ Hito 0.5 |
| Sprint 4 — Pipeline Completo | Semana 4 MVP | 24–30 jun. 2025 | Volumetría funcional (Hito 2\) |
| Sprint 5 — Estabilización | Semana 5 MVP | 1–5 jul. 2025 | MVP completo y estable (Hito 3\) |
| **ENTREGA FINAL** | Fin del proyecto | **6 jul. 2025** | MVP \+ Informe Final \+ Video Demostrativo |

## **6.2 Carta Gantt Semanal del MVP (Semanas 1–5)**

Las 5 semanas del MVP comenzaron el 3 de junio de 2025\. Cada semana corresponde a un Sprint con su Sprint Goal, historias de usuario comprometidas, hitos y buffers.

| Sprint | Período | Sprint Goal | Historias | Hito | Entregable Clave | Buffer |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| **S-1** | 3–9 jun. | Reducir riesgos tecnológicos críticos | PB-01: Carga de imágenesPB-04: Integrar NodeODM | Hito 0: Docker \+ NodeODM operativos | Primera nube de puntos generada | 2h |
| **S-2** | 10–16 jun. | Obtener escalado métrico confiable | PB-02: Detectar guíaPB-03: Aplicar escala | Hito 1: Detección ≥90%, error ≤5% | Calibración espacial funcional | 2h |
| **S-3** | 17–23 jun. | Generar geometría 3D válida | PB-05: Generar nube de puntosPB-06: Generar malla 3D | Hito 0.5: Volumen preliminar ≤25% | Malla cerrada apta para volumetría | 3h |
| **S-4** | 24–30 jun. | Completar flujo funcional end-to-end | PB-07: Calcular volumenPB-08: Mostrar resultadoPB-09: Exportar JSON | Hito 2: Error ≤15% sobre Ground Truth | Pipeline completo funcional | 3h |
| **S-5** | 1–5 jul. | Corrección y validación final | PB-10: Exportar CSVEstabilización general | Hito 3: MVP completo y estable | Sistema validado y documentado | 7h |
| **CIERRE** | **6 jul. 2025** | **Entrega Final** | — | **Todos los hitos** | Informe Final \+ Video Demostrativo | — |

## **6.3 Hitos del Proyecto**

| Hito | Nombre | Sprint / Fecha | Criterio de Éxito |
| ----- | ----- | ----- | ----- |
| Hito 0 | Validación Técnica Inicial | Sprint 1 / 9 jun. | Docker, NodeODM y dataset operativos. Primera nube de puntos generada. |
| Hito 0.5 | Validación Volumétrica Preliminar | Sprint 3 / 23 jun. | Volumen preliminar calculado con error ≤25%. Si \>25%: activar plan de contingencia R4. |
| Hito 1 | Calibración Espacial Funcional | Sprint 2 / 16 jun. | Detección guía ≥90%. Error de escala ≤5%. |
| Hito 2 | Volumetría Funcional | Sprint 4 / 30 jun. | Error volumétrico ≤15% sobre Ground Truth. |
| Hito 3 | MVP Completo y Estable | Sprint 5 / 5 jul. | Todos los criterios de éxito cumplidos. Despliegue Docker Compose validado. |
| **Hito Final** | **Entrega del Proyecto** | **6 jul. 2025** | MVP \+ Informe Final \+ Video Demostrativo entregados. |

## **6.4 Capacidad y Distribución de Horas**

| Parámetro | Valor |
| ----- | ----- |
| Horas semanales disponibles | 25 horas |
| Duración MVP | 5 semanas |
| Capacidad total | 125 horas |
| Horas estimadas en backlog | 108 horas |
| Reserva operacional | 17 horas (13.6%) |
| Equipo | Un único desarrollador: Fabián Matus Alarcón |

# **7\. Informe Final y Video Demostrativo**

## **7.1 Informe Final**

El Informe Final se entrega el 6 de julio de 2025, simultáneamente con el MVP y el Video Demostrativo. Constituye la documentación técnica y científica completa del proyecto.

### **Contenido del Informe Final**

* Resumen ejecutivo del proyecto y resultados obtenidos

* Problemática, objetivos y alcance consolidados

* Estado del arte: referencias bibliográficas y análisis tecnológico

* Descripción completa de la arquitectura del sistema (5 vistas)

* Pipeline técnico: cada etapa, sus productos y métricas de calidad

* Resultados del MVP: error volumétrico obtenido vs. Ground Truth

* Análisis de hitos: cumplimiento de Hito 0, 0.5, 1, 2 y 3

* Gestión de riesgos: riesgos materializados y mitigaciones aplicadas

* Conclusiones y trabajo futuro (integración YOLOv8, ERP, drones reales)

* Bibliografía científica completa (formato APA)

## **7.2 Video Demostrativo**

El Video Demostrativo se entrega el 6 de julio de 2025\. Muestra el sistema ForestVol en funcionamiento completo, desde la carga de imágenes hasta la exportación del reporte volumétrico.

### **Contenido del Video**

* Presentación del problema y motivación (30 seg.)

* Carga y validación de imágenes en la interfaz web

* Ejecución del pipeline: calibración, reconstrucción 3D, volumetría

* Visualización del modelo 3D con Three.js en el frontend

* Resultado final: volumen en m³ y comparación con Ground Truth

* Exportación de reporte en JSON y CSV

* Despliegue con Docker Compose (comandos de inicio)

# **8\. Gestión de Riesgos**

Escala: Probabilidad 1–5 · Impacto 1–5 · Nivel \= Prob × Impacto.

| ID | Riesgo | Prob. | Imp. | Nivel | Mitigación | Control |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| R1 | NodeODM falla o no levanta | 4 | 5 | 20 | Hito 0 obligatorio en Sprint 1\. Si falla: evaluar alternativa o reducir resolución. Decisión en 4h máximo. | Hito 0 |
| R2 | Guía de calibración no detectada | 3 | 4 | 12 | Escalado manual de respaldo siempre disponible. Umbral de confianza OpenCV configurable. | Sprint 2 |
| R3 | Malla inválida o no cerrada | 4 | 4 | 16 | Reparación automática Open3D. Si persiste: reducir densidad de nube de puntos. | Sprint 3 |
| R4 | Error volumétrico \> 15% al final | 3 | 5 | 15 | Hito 0.5 detecta en Sprint 3\. Plan B: ajustar calibración, reducir tolerancia a 20% o documentar limitación técnica. | Hito 0.5 |
| R5 | Integración compleja entre módulos | 4 | 4 | 16 | Buffers distribuidos por sprint. Contrato de interfaz definido al inicio de cada sprint. | Por sprint |
| R6 | Hardware insuficiente | 2 | 3 | 6 | Reducir tamaño del dataset o resolución de imágenes. | Sprint 1 |
| R7 | Dataset insuficiente o pequeño | 3 | 5 | 15 | Validación del dataset en Hito 0 con métricas mínimas (densidad, cobertura). | Hito 0 |
| R8 | Dataset no representativo | 3 | 4 | 12 | Comparación contra múltiples Ground Truth. Documentar limitaciones. | Sprint 5 |

| Nivel | Rango | Acción |
| ----- | ----- | ----- |
| **ALTO** | ≥ 16 | Acción inmediata requerida |
| **MEDIO** | 10 – 15 | Monitorear activamente |
| **BAJO** | \< 10 | Registrar y revisar |

# **9\. Definición Formal de Éxito**

El MVP será considerado exitoso cuando cumpla todos los siguientes criterios:

| ✓ Procesamiento de al menos 10 imágenes fotogramétricas. ✓ Reconstrucción de una geometría 3D válida y cerrada. ✓ Cálculo de volumen expresado en m³. ✓ Error volumétrico ≤ 15% respecto al Ground Truth. ✓ Flujo completo ejecutado sin intervención técnica manual. ✓ Despliegue funcional mediante Docker Compose en hardware académico convencional. |
| :---- |

## **9.1 Criterio de Pivote Post-MVP**

| Condición al Final del MVP | Decisión | Acción |
| ----- | ----- | ----- |
| Error ≤ 15% | **MVP EXITOSO** | Documentar y entregar. Hipótesis validada. |
| Error 15% – 20% | **MVP ACEPTABLE** | Documentar limitaciones técnicas. Justificar mediante literatura forestal. Proponer sprint de ajuste. |
| Error \> 20% | **MVP FALLIDO** | Detener desarrollo de funcionalidades. Revisar pipeline de calibración. Reformular hipótesis. |

| Nota: Si el Hito 0.5 (Sprint 3\) detecta error \> 25%, se activa el plan de contingencia de R4 antes de continuar con Sprint 4, evitando trabajo desperdiciado. |
| :---- |

