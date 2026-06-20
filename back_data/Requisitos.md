# Requisitos

Integrante: Fabián Matus Alarcón

# Requisitos Funcionales

Cada requisito se identifica con un código único (RF-XX), nombre descriptivo, descripción detallada y nivel de prioridad (Alta / Media / Baja). Los requisitos exploratorios del dominio remedial (IA/YOLOv8) se señalan explícitamente.

## Módulo de Ingesta de Imágenes

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RF-01 | Carga de imágenes aéreas | El sistema debe aceptar la ingesta de conjuntos de imágenes fotogramétricas en formato JPG/PNG capturadas por drones comerciales con sensor RGB estándar. La interfaz de carga debe soportar múltiples archivos simultáneamente. | Alta |
| RF-02 | Validación de formato | El sistema debe validar que los archivos ingresados correspondan a formatos de imagen admitidos (JPG, PNG) y rechazar archivos inválidos con un mensaje de error descriptivo. | Alta |

## Módulo de Calibración Espacial

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RF-03 | Detección de guía de calibración | El sistema debe utilizar OpenCV para detectar automáticamente los contornos de la guía física de calibración de 50×50 cm dispuesta en el acopio dentro del conjunto de imágenes ingresadas. | Alta |
| RF-04 | Aplicación de escala real | A partir de la guía detectada, el sistema debe calcular y aplicar matrices de transformación geométrica que otorguen escala métrica real al modelo 3D generado, sin necesidad de GCPs ni RTK. | Alta |
| RF-05 | Alerta de guía no detectada | Si el sistema no puede detectar la guía de calibración en ninguna imagen del set, debe notificar al operador con un mensaje de advertencia claro antes de continuar el procesamiento. | Alta |

## Módulo de Procesamiento Fotogramétrico

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RF-06 | Generación de nube de puntos | El sistema debe implementar un flujo SfM/MVS a través de OpenDroneMap/NodeODM para procesar el conjunto de imágenes calibradas y generar una nube de puntos densa que represente la geometría 3D del castillo. | Alta |
| RF-07 | Generación de malla tridimensional | A partir de la nube de puntos, el sistema debe construir una malla 3D cerrada (mesh) del castillo de madera como paso previo al cálculo volumétrico. | Alta |

## Módulo de Cálculo Volumétrico

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RF-08 | Cálculo de volumen aparente | El sistema debe calcular automáticamente el volumen aparente del castillo de madera utilizando la malla 3D generada y herramientas de manipulación espacial de Open3D. Este es el resultado volumétrico principal y definitivo reportado al operador. | Alta |
| RF-09 | Reporte del resultado volumétrico | El sistema debe exponer el resultado del cálculo como un valor numérico en metros cúbicos (m³), mostrarlo en la interfaz web y hacerlo disponible para exportación. | Alta |

## Módulo de Exportación

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RF-10 | Exportación de reporte en JSON | El sistema debe permitir la exportación del resultado volumétrico y metadatos del procesamiento (fecha, número de imágenes, escala aplicada) en formato JSON. | Alta |
| RF-11 | Exportación de reporte en CSV | El sistema debe permitir la exportación del resultado volumétrico en formato CSV para su uso en herramientas externas de análisis o registro operativo. | Media |

## Módulo de Visualización Web

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RF-12 | Visualización de métricas | La interfaz web debe mostrar junto al modelo 3D las métricas de resultado: volumen calculado (m³), escala aplicada y estado del procesamiento. | Alta |

# Requisitos No Funcionales

## Rendimiento

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RNF-01 | Procesamiento en CPU | El núcleo de procesamiento fotogramétrico debe ejecutarse eficientemente sobre CPU estándar sin requerir GPU con soporte CUDA. | Alta |
| RNF-02 | Reducción de tiempo operativo | El sistema debe reducir drásticamente los tiempos de medición volumétrica en terreno respecto al método manual, como objetivo general de rendimiento operativo. | Alta |

## Portabilidad y Despliegue

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RNF-03 | Contenedores Docker | El motor fotogramétrico NodeODM debe desplegarse mediante contenedores Docker nativos, garantizando escalabilidad y reproducibilidad en distintos entornos de hardware y sistema operativo. | Alta |
| RNF-04 | Stack open-source | Toda la arquitectura tecnológica del sistema debe basarse en tecnologías, frameworks y librerías de código abierto, eliminando dependencias de licencias comerciales privativas. | Alta |

## Mantenibilidad

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RNF-05 | Backend en Python 3.x | El backend lógico, la orquestación de la infraestructura de datos y la integración de microservicios deben estar programados íntegramente en Python versión 3.x para garantizar interoperabilidad transversal de las librerías analíticas. | Alta |
| RNF-06 | Arquitectura desacoplada | La interfaz de usuario (SPA en Vue.js o React) debe operar de manera completamente independiente del motor analítico de backend, comunicándose únicamente a través de la API REST. | Alta |

## Seguridad Operacional

| ID | Nombre | Descripción | Prioridad |
| :---- | :---- | :---- | :---- |
| RNF-07 | Seguridad laboral | El sistema debe permitir que el cálculo volumétrico completo se realice de forma remota, sin necesidad de que el personal ingrese al área de acopio durante el proceso de medición, reduciendo la exposición a terrenos irregulares o peligrosos. | Alta |
| RNF-08 | Independencia de conectividad absoluta | El procesamiento debe ejecutarse basándose únicamente en métricas relativas provistas por la guía de calibración física, haciendo innecesaria cualquier conectividad RTK o el uso de GCPs absolutos en terreno. | Alta |

# Trazabilidad

## Requisitos funcionales

| ID Requisito | Nombre del Requisito | Caso de Uso Asociado |
| :---- | :---- | :---- |
| RF-01 | Carga de imágenes aéreas | UC-01 |
| RF-02 | Validación de formato | UC-01 |
| RF-03 | Detección para calibración espacial | UC-02 |
| RF-04 | Aplicación de escala espacial | UC-02 |
| RF-05 | Alerta de fallo en calibración espacial | UC-02 |
| RF-06 | Generación de nube de puntos | UC-03 |
| RF-07 | Generación de malla tridimensional | UC-03 |
| RF-08 | Calcular volumen aparente | UC-04 |
| RF-09 | Reporte del volumen aparente | UC-04, UC-05 |
| RF-10 | Exportación de reporte en JSON | UC-06 |
| RF-11 | Exportación de reporte en CSV | UC-06 |
| RF-12 | Visualización de métricas | UC-05 |

## 

## Requisitos no funcionales

| ID Requisito | Nombre del Requisito | Alcance / Casos de Uso Impactados |
| :---- | :---- | :---- |
| RNF-01 | Procesamiento en CPU | UC-03, UC-04 |
| RNF-02 | Reducción de tiempo operativo | Transversal |
| RNF-03 | Contenedores Docker | UC-03, UC-04 |
| RNF-04 | Stack open-source | Transversal |
| RNF-05 | Backend en Python 3.x | Transversal |
| RNF-06 | Arquitectura desacoplada | Transversal |
| RNF-07 | Seguridad laboral | UC-01 |
| RNF-08 | Independencia de conectividad | UC-02, UC-03, UC-04 |

# 

# 

# Criterios de aceptación

## Requisitos funcionales

### Módulo de Ingesta de Imágenes

| ID | Requisito | Criterio de Aceptación Medible | Método de Verificación | Resultado Esperado |
| :---- | :---- | :---- | :---- | :---- |
| RF-01 | Carga de imágenes aéreas | El sistema acepta la carga de al menos 20 imágenes JPG/PNG simultáneas de hasta 24 MP sin errores de memoria ni corrupción de archivos. | Prueba funcional: cargar un set de 20+ imágenes reales del vuelo y verificar que todas queden registradas en el sistema. | 100% de las imágenes cargadas disponibles para procesamiento sin pérdida de datos. |
| RF-02 | Validación de formato | El sistema rechaza archivos con extensiones no permitidas (PDF, DOCX, MP4, etc.) y muestra un mensaje de error descriptivo en menos de 2 segundos. | Prueba de borde: intentar cargar archivos de formato inválido y registrar la respuesta del sistema. | Mensaje de error visible con indicación del archivo rechazado y formato esperado. Ningún archivo inválido ingresa al flujo de procesamiento. |

### Módulo de Calibración Espacial

| ID | Requisito | Criterio de Aceptación Medible | Método de Verificación | Resultado Esperado |
| :---- | :---- | :---- | :---- | :---- |
| RF-03 | Detección para calibración espacial  | OpenCV detecta correctamente los contornos de la guía de 50×50 cm en condiciones normales de iluminación (sin sombras extremas ni obstrucciones totales) en al menos el 90% de las imágenes donde la guía es visible. | Prueba con set de imágenes reales: comparar detecciones automáticas vs. presencia visual confirmada manualmente. | Tasa de detección ≥ 90% sobre imágenes donde la guía es visualmente identificable por un humano. |
| RF-04 | Aplicación de escala espacial | La escala aplicada al modelo 3D produce una medida de referencia conocida (la guía de 50 cm) con un error no superior al 5% respecto a su dimensión real física. | Medir el lado de la guía en el modelo 3D generado y comparar contra el valor real de 50 cm. | Longitud medida en el modelo: entre 47,5 cm y 52,5 cm (±5% de 50 cm). |
| RF-05 | Alerta de fallo en calibración espacial | Si el sistema no detecta la guía en ninguna imagen del set, emite una advertencia clara en la interfaz antes de continuar y el proceso no avanza al cálculo volumétrico sin confirmación del operador. | Prueba con set de imágenes sin la guía: verificar que el sistema detiene el flujo y muestra el aviso. | Mensaje de advertencia visible. El sistema requiere confirmación o aborta antes de cubicar. |

### Módulo de Procesamiento Fotogramétrico

| ID | Requisito | Criterio de Aceptación Medible | Método de Verificación | Resultado Esperado |
| :---- | :---- | :---- | :---- | :---- |
| RF-06 | Generación de nube de puntos | A partir de las imágenes, NodeODM genera una nube de puntos densa que cubre la geometría del acopio sin vacíos mayores al 10% del área. | Inspección y revisión de la densidad de puntos del archivo resultante mediante Open3D. | Nube de puntos densa generada sin errores de proceso. Cobertura superficial ≥ 90% del castillo. |
| RF-07 | Generación de malla tridimensional | El sistema produce una malla 3D cerrada (mesh) a partir de la nube de puntos, apta para el cálculo volumétrico. | Análisis geométrico con Open3D: verificar la propiedad de watertightness (malla estanca/cerrada). | Malla cerrada sin agujeros en más del 5% de la superficie. Apta para cálculo volumétrico. |

### Módulo de Cálculo Volumétrico

| ID | Requisito | Criterio de Aceptación Medible | Método de Verificación | Resultado Esperado |
| :---- | :---- | :---- | :---- | :---- |
| RF-08 | Calcular volumen aparente | El volumen calculado automáticamente mediante Open3D difiere en un máximo de ±15% respecto a la medición física tradicional de control. | Contraste directo: comparar el resultado arrojado por ForestVol contra la cubicación manual con cinta métrica. | Margen de error acumulado ≤ 15% respecto a la medición física de terreno.. |
| RF-009 | Reporte del volumen aparente | El resultado final en metros cúbicos (m³) se expone automáticamente en la interfaz web al terminar el cálculo. | Verificación visual en el panel web tras completar de manera exitosa un flujo completo. | Valor numérico en m³ explícitamente visible en pantalla sin requerir acciones adicionales del usuario. |

### Módulo de Exportación

| ID | Requisito | Criterio de Aceptación Medible | Método de Verificación | Resultado Esperado |
| :---- | :---- | :---- | :---- | :---- |
| RF-10 | Exportación de reporte en JSON | El archivo JSON descargado contiene de forma estricta los campos estructurados: volumen\_m3, fecha\_proceso, num\_imagenes y escala\_aplicada. | Descargar el reporte y validar su estructura con un formateador/validador JSON estándar.. | Estructura JSON válida, limpia, parseable y con los 4 campos obligatorios poblados correctamente. |
| RF-11 | Exportación en CSV | El archivo CSV exportado contiene encabezados en la primera fila y al menos el campo de volumen en m³, y puede abrirse correctamente en Microsoft Excel o LibreOffice Calc. | Exportar el archivo CSV y abrirlo directamente en Microsoft Excel o LibreOffice Calc. | Apertura correcta sin errores de delimitación, con los datos legibles distribuidos en columnas. |

### Módulo de Visualización Web

| ID | Requisito | Criterio de Aceptación Medible | Método de Verificación | Resultado Esperado |
| :---- | :---- | :---- | :---- | :---- |
| RF-12 | Visualización de métricas | El panel de la interfaz web presenta simultáneamente el volumen aparente (m³), la escala aplicada y la cantidad de imágenes. | Inspección visual directa sobre la interfaz de usuario al finalizar el procesamiento de un set. | Panel resumen de métricas visible, limpio y actualizado de forma sincronizada con el backend. |

