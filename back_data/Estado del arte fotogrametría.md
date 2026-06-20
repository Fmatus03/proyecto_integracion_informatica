# **Estado del arte fotometría** 

Nombre: Fabián Matus Alarcón 

# **Estado del Arte Científico: Tecnologías Fotogramétricas y Visión Computacional para la Estimación de Volumen de Madera** 

## **1\. Introducción y Contexto Problemático** 

La cuantificación precisa del volumen de madera apilada es un proceso crítico en la cadena de suministro, comercialización forestal y la planificación de la logística de transporte. Tradicionalmente, este procedimiento ha dependido de mediciones manuales que consisten en medir el contorno de la pila (ancho, alto y largo) para obtener un "volumen aparente" o estéreo, al cual se le aplica un factor de conversión para estimar el "volumen sólido" real de la madera, descontando los espacios de aire y la corteza. 

Estas técnicas manuales, además de ser laboriosas, lentas y propensas a riesgos de seguridad industrial, son altamente susceptibles a sesgos y errores humanos derivados de la irregularidad geométrica de los acopios. En la búsqueda de la eficiencia operativa y la transparencia en las transacciones comerciales, la literatura científica reciente (2023-2025) evidencia una transición acelerada hacia el uso de tecnologías de teledetección (Remote Sensing), fotogrametría digital y, de manera muy destacada, la Inteligencia Artificial (IA). Este documento presenta el estado actual de la investigación en métodos automatizados de bajo costo, validando la viabilidad técnica de sistemas basados en procesamiento de imágenes y modelado 3D frente a técnicas tradicionales y equipos de alto costo. 

## **2\. Democratización del Hardware: Eficiencia de Sensores RGB Estándar**

El primer paso hacia la automatización masiva es la captura de datos en terreno. Históricamente, la digitalización de inventarios forestales requería equipos aéreos o terrestres costosos, pero la tendencia científica demuestra que ya no es estrictamente necesario depender de hardware especializado para obtener resultados precisos y comercialmente aceptables.  
El estudio de Ucar et al. (2024) aborda directamente esta premisa al evaluar el uso de sensores ópticos comerciales para medir acopios de madera en prácticas forestales en Turquía. La investigación analizó 21 pilas de troncos, comparando las mediciones manuales tradicionales frente a sistemas foto-ópticos basados en cámaras estándar (como las integradas en smartphones).

* **Hallazgos Estadísticos:** Los autores encontraron una fuerte correlación entre el volumen de madera sólida medido tradicionalmente y el estimado por las aplicaciones. Lo mismo ocurrió con el conteo total de troncos, donde las estimaciones no presentaron diferencias estadísticamente significativas frente al conteo manual. Sin embargo, el estudio notó discrepancias en la medición del diámetro medio, señalando que la detección de los bordes exactos de la corteza sigue siendo un desafío óptico que requiere calibración.  
* **Implicancia para la Ingeniería de Datos:** Este hallazgo respalda científicamente que las cámaras RGB estándar (como las integradas en teléfonos inteligentes o drones comerciales de bajo costo) son dispositivos de entrada (input) completamente válidos y robustos. Esto permite diseñar arquitecturas de software altamente escalables y de bajo costo operativo. Al usar vehículos aéreos no tripulados (UAVs) comerciales, se elimina la barrera de entrada económica, democratizando el acceso a la cubicación digital masiva para productores forestales.

**3\. Calidad Métrica y Calibración: Métodos Foto-Ópticos vs. Tecnología LiDAR**   
Para que un conjunto de imágenes 2D sirva para el cálculo de volúmenes volumétricos reales, es imperativo dotar al modelo de escala y percepción de profundidad. La literatura ha validado los métodos de calibración óptica y los ha puesto a prueba frente a tecnologías activas de emisión láser.

La investigación de Purfürst et al. (2023) es pionera en este aspecto, realizando una exhaustiva comparativa entre nueve métodos distintos de medición en 47 acopios de madera (con volúmenes que oscilaban entre 8.9 y 209.3 m³). El estudio abarcó técnicas manuales, métodos foto-ópticos de 2.5D y 3D (fotogrametría monocular que requiere costura o stitching de imágenes) y escáneres láser, incluyendo LiDAR portátil tradicional y los recientes módulos iPad-LiDAR.

* **Precisión y Justificación de Escala:** El estudio demostró que los métodos fotogramétricos logran precisiones volumétricas comparables a los costosos sistemas LiDAR, e incluso superan en detalle a las mediciones manuales que asumen formas geométricas perfectas inexistentes en la realidad. Para lograr esta precisión sin sensores de tiempo de vuelo, los sistemas ópticos calculan la geometría espacial basándose en referencias físicas de dimensiones conocidas instaladas en la escena.  
* **Implicancia Técnica y Operativa:** Esto constituye la justificación empírica ineludible para el uso de marcos, reglas o guías físicas en terreno (por ejemplo, un marco de calibración de 50x50 cm). El paper demuestra que no es imperativo usar sensores de profundidad (LiDAR) transportados en el dron si se aplica un correcto procesamiento fotogramétrico respaldado por una métrica local de referencia.

**4\. Reconstrucción 3D y Fotogrametría: La Irrelevancia de Coordenadas Absolutas (GCPs)**  
Una vez capturadas las imágenes calibradas mediante el dron, los algoritmos de fotogrametría como Structure from Motion (SfM) y Multi-View Stereo (MVS) se encargan de encontrar puntos homólogos entre las fotografías para generar densas nubes de puntos y mallas volumétricas. Un debate técnico recurrente ha sido si estos modelos aéreos requieren un amarre topográfico riguroso para garantizar la precisión de sus volúmenes.

El estudio de Araújo Júnior et al. (2025) resolvió esta interrogante al evaluar levantamientos aéreos sobre 24 pilas de madera de *Eucalyptus sp*. La investigación comparó planes de vuelo a 50 y 80 metros de altura (con 70% y 80% de solapamiento frontal y lateral, respectivamente) y analizó las reconstrucciones con y sin el uso de 35 Puntos de Control Terrestre (GCPs), utilizando pruebas no paramétricas de Friedman y Nemenyi.

* **Resultados sobre el Volumen:** Si bien el procesamiento con GCPs lógicamente resultó en valores menores de Error Cuadrático Medio (RMSE) respecto al posicionamiento global absoluto, las estimaciones de volumen bruto de cada acopio fueron estadísticamente similares, independientemente de si se usaron o no puntos de control topográfico.  
* **Implicancia en el Pipeline de Software:** Este estudio es el pilar fundamental para arquitecturas de software orientadas al análisis local. Valida que los motores 3D (como AliceVision Meshroom u OpenDroneMap) pueden calcular el volumen del acopio basándose únicamente en métricas relativas (la escala otorgada por la referencia física), haciendo completamente innecesario el uso de drones con RTK o el despliegue de receptores GPS en terreno, lo que acelera drásticamente el flujo de trabajo operativo.

**5\. Inteligencia Artificial: Segmentación de Instancias y Modelado de Diámetros**   
Mientras que la fotogrametría resuelve el cálculo del volumen aparente (el contorno de la pila), la frontera actual del estado del arte se encuentra en el procesamiento de la información visual mediante Deep Learning para automatizar el cálculo del volumen sólido real, eliminando el uso de factores de conversión genéricos y la intervención humana en el conteo.

El innovador estudio de Goycochea Casas et al. (2024) propone un modelo integral para cuantificar el volumen sólido utilizando redes neuronales convolucionales, específicamente implementando la arquitectura YOLOv8 (You Only Look Once, versión 8\) para la tarea de segmentación de instancias.

* **Mecanismo de Segmentación:** A diferencia de la simple detección de cajas delimitadoras (bounding boxes), el modelo YOLOv8 implementado logra perfilar y generar una máscara poligonal exacta sobre el área de cada cara transversal del tronco (log end) expuesta en el frente de la pila.  
* **Del Pixel a la Volumetría Sólida:** El aporte más significativo de esta investigación es la metodología post-segmentación. Una vez que la IA mide el diámetro de cada tronco visible, los autores aplican modelos estadísticos de distribución de diámetros (como la función de probabilidad de Weibull) junto con ecuaciones de perfil (taper models). Esto permite extrapolar la geometría tridimensional de cada tronco individual hacia el interior de la pila, estimando el volumen sólido total con una precisión comparable a la medición destructiva tronco por tronco.  
* **Impacto en la Arquitectura de Software:** Este documento es la pieza final del rompecabezas tecnológico. Demuestra que es científicamente válido y operativamente superior integrar algoritmos de visión computacional para automatizar la extracción de datos biométricos. Consolida la viabilidad de un pipeline completo de "detección-segmentación-modelado matemático", proporcionando una solución comercial robusta, auditable y extremadamente rápida frente a la obsolescencia de las mediciones estéreo tradicionales.

**6\. Conclusión y Síntesis de Viabilidad**   
La revisión crítica de la literatura científica más reciente (2023-2025) justifica de manera categórica el desarrollo de soluciones informáticas para la medición de inventarios forestales basadas exclusivamente en vuelos de drones, algoritmos de visión computacional y fotogrametría. El estado del arte actual convalida una arquitectura de datos donde:

1. **Hardware Accesible:** Se utilizan cámaras RGB estándar (presentes en drones comerciales de bajo costo) como sensores de captura aéreos viables, garantizando escalabilidad operativa sin depender de equipos de grado topográfico (Ucar et al., 2024).  
2. **Calibración Local:** Se emplean referencias físicas de dimensiones conocidas para escalar los modelos fotogramétricos, logrando precisiones que compiten con tecnologías láser activas como el LiDAR (Purfürst et al., 2023).  
3. **Procesamiento Volumétrico:** La aplicación de algoritmos SfM/MVS permite reconstruir la geometría tridimensional de las pilas de madera sin depender de infraestructuras topográficas costosas o GCPs absolutos (Araújo Júnior et al., 2025).  
4. **Análisis Automatizado:** La integración de redes neuronales de última generación (YOLOv8) permite la segmentación de instancias y la aplicación de funciones de distribución diamétrica para calcular el volumen sólido individual (Goycochea Casas et al., 2024).

La convergencia y orquestación de estas cuatro áreas tecnológicas define el estándar actual, asegurando que un sistema de software basado en capturas con drones no solo es factible desde la Ingeniería de Datos, sino que representa el futuro inmediato para la eficiencia operativa del sector maderero.

# **Parte 2: Estado del Arte Tecnológico: Herramientas, Frameworks y Arquitectura de Software** 

**1\. Introducción al Ecosistema Tecnológico**   
Mientras que la viabilidad científica de la medición foto-óptica y volumétrica mediante drones ha sido validada en la literatura forestal reciente, la materialización de estos conceptos requiere el ensamblaje de una arquitectura de software compleja. Este "pipeline" de procesamiento debe ser capaz de ingerir imágenes crudas aéreas, calibrarlas espacialmente, reconstruir modelos tridimensionales, segmentar elementos individuales mediante Inteligencia Artificial y calcular métricas volumétricas precisas. El presente apartado revisa el estado del arte de las tecnologías, librerías y lenguajes de programación disponibles para cada fase del procesamiento de datos, contrastando soluciones comerciales frente a alternativas de código abierto (Open-Source).

**2\. Motores de Reconstrucción 3D (Generación de Nube de Puntos y Malla)**   
El núcleo algorítmico para la digitalización de los acopios de madera radica en los motores de fotogrametría que aplican técnicas de Structure from Motion (SfM) y Multi-View Stereo (MVS). El mercado actual ofrece una dicotomía clara entre soluciones privativas altamente automatizadas y proyectos de código abierto orientados a la investigación y el despliegue escalable.

**2.1. Alternativas de Código Abierto (Open-Source)**   
El ecosistema Open-Source ha madurado hasta alcanzar precisiones equiparables a los estándares comerciales, ofreciendo distintas filosofías de integración:

* **AliceVision Meshroom:** Según Griwodz et al. (2021), este framework destaca por su arquitectura basada en nodos (node-based pipeline). Esto permite a los ingenieros de datos inspeccionar y modificar cada paso del proceso fotogramétrico de forma visual y modular. Sin embargo, presenta una alta dependencia de hardware privativo, requiriendo específicamente tarjetas gráficas compatibles con la tecnología CUDA de NVIDIA, lo que puede representar un cuello de botella para despliegues en servidores de bajo costo.  
* **OpenDroneMap (WebODM / NodeODM):** Como detalla Toffanin (2019), este ecosistema ha revolucionado la accesibilidad a la fotogrametría aérea. Su principal ventaja arquitectónica es su naturaleza nativa en contenedores (Docker), lo que garantiza una alta escalabilidad y un despliegue sin fricciones. A diferencia de Meshroom, ODM está altamente optimizado para ejecutarse en CPU si no hay GPU disponible, haciéndolo ideal para procesar vuelos de drones en entornos de infraestructura agnóstica y sin costos de licenciamiento.  
* **MicMac:** Desarrollado por el Instituto Geográfico Nacional de Francia (Rupnik et al., 2017), es una solución fotogramétrica de extrema precisión. Si bien es el estándar de oro en términos de rigor científico metrológico, su arquitectura basada casi exclusivamente en línea de comandos y su altísima curva de aprendizaje lo convierten en una herramienta compleja de integrar en pipelines automatizados de desarrollo rápido.

**2.2. Alternativas Comerciales (Baseline de Contraste)**   
Para contextualizar el rendimiento de las herramientas libres, es imperativo mencionar los estándares comerciales que dominan la industria:

* **Agisoft Metashape:** Evaluado extensamente en la literatura (Benassi et al., 2017), es considerado el Gold Standard del procesamiento local. Ofrece algoritmos propietarios extremadamente eficientes. Sin embargo, su limitante para la construcción de nuevas plataformas tecnológicas es su modelo de licenciamiento privativo, cuyo costo resulta prohibitivo para el desarrollo de soluciones escalables.  
* **Pix4D / Drone Deploy:** Analizados en estudios comparativos (Sona et al., 2014), estas plataformas representan el paradigma del Software as a Service (SaaS). Aunque eliminan la necesidad de procesamiento local mediante computación en la nube, introducen una dependencia crítica de la conexión a internet (inviable en operaciones forestales remotas) y operan bajo altos costos recurrentes de suscripción.

**3\. Librerías de Procesamiento Geométrico y Cálculo Volumétrico** 

Una vez generada la nube de puntos o la malla 3D de la pila de madera, el sistema debe ser capaz de aislar el área de interés e interrogar geométricamente el modelo para extraer el volumen (metros cúbicos). Para ello, existen potentes librerías de manipulación espacial: 

● **CloudCompare:** Reconocida mundialmente, Girardeau-Montaut (2011) presenta CloudCompare como la herramienta de referencia para el procesamiento masivo de nubes de puntos y mallas. Es excepcionalmente robusta para el cálculo de volumen 2.5D (calculando la diferencia volumétrica entre la malla de la pila y un plano de referencia del suelo terrestre). No obstante, aunque posee capacidades de línea de  
comandos (CLI), su automatización pura como un microservicio silencioso sin interfaz gráfica (Headless) puede ser más compleja de orquestar que una librería de programación pura. 

● **Open3D:** Zhou, Park y Koltun (2018) introdujeron Open3D como una biblioteca moderna diseñada específicamente para el procesamiento de datos 3D. Su gran ventaja para el desarrollo es su API nativa en Python y C++. Permite la manipulación directa de tensores 3D, limpieza topológica y, críticamente, el cálculo algorítmico de mallas envolventes convexas (*Convex Hull*), lo cual es fundamental para calcular el volumen aparente de formas irregulares como los acopios de troncos. 

● **PDAL (Point Data Abstraction Library):** Como señalan Butler et al. (2021), PDAL actúa como el "puente de traducción" definitivo para datos espaciales. Si el proyecto se enfrenta a nubes de puntos masivas, PDAL ofrece un rendimiento incomparable para el filtrado topológico, decantación (*downsampling*) y transformación de coordenadas estructuradas a través de *pipelines* en formato JSON. 

● **Trimesh:** Dawson-Haggerty et al. (2019) desarrollaron esta librería en Python enfocada exclusivamente en la manipulación de polígonos. Es fundamental cuando se busca un enfoque volumétrico estrictamente basado en mallas triangulares cerradas o estancas (*watertight meshes*), permitiendo operaciones booleanas (intersecciones) y cálculos de inercia y volumen directamente sobre el objeto 3D sin depender de un plano de elevación base. 

**4\. Visión Computacional e Inteligencia Artificial (Detección y Calibración)** 

El análisis visual de la madera requiere un enfoque híbrido: métodos deterministas para resolver la calibración métrica (escala espacial) y métodos probabilísticos (IA) para lidiar con el ruido orgánico de la madera. 

● **OpenCV:** Según Bradski (2000), la librería OpenCV es el pilar histórico de la visión computacional. En el contexto de este problema, su alta eficiencia computacional y bajo consumo de recursos la hacen idónea para tareas de preprocesamiento clásico. Es la herramienta indicada para detectar la "guía física de calibración" (ej. un marco de 50x50 cm) mediante la detección de contornos, umbralización de color y la aplicación de matrices de transformación de perspectiva, otorgando escala real a los píxeles antes del análisis complejo. 

● **YOLO (Ultralytics):** Para el conteo e identificación de las caras de los troncos, los métodos clásicos fallan debido a la variabilidad de la corteza, la iluminación y la oclusión. Jocher et al. (2023) con las arquitecturas YOLOv8 (y sus evoluciones posteriores), basadas en los principios de *You Only Look Once* (Redmon et al., 

2016), representan la vanguardia en precisión y robustez. Estos modelos de redes neuronales convolucionales permiten detectar y perfilar (segmentación de instancias) las caras de los troncos ignorando el ruido de fondo. Su adopción requiere mayor poder de cómputo (idealmente aceleración por tensores), pero garantiza una precisión crítica para el cálculo de diámetros. 

● **PyTorch / TensorFlow:** Paszke et al. (2019) exponen PyTorch como una librería de aprendizaje profundo de alto rendimiento. En el diseño arquitectónico de una aplicación forestal, frameworks de bajo nivel como PyTorch o TensorFlow rara vez se  
exponen en la capa de negocio lógico; sin embargo, se justifican como las dependencias de infraestructura primordiales (*backend engine*) sobre las cuales se ejecutan los modelos pre-entrenados de segmentación como YOLO. 

**5\. Lenguajes de Programación y Orquestación de Infraestructura** 

La elección de los lenguajes fundamentales dicta la velocidad de iteración y la mantenibilidad a largo plazo del sistema de ingeniería de datos. 

● **Python (3.x):** Considerado por Millman y Aivazis (2011) como el estándar de facto para la ciencia de datos, Python actúa como el "pegamento" perfecto en ecosistemas heterogéneos. El criterio primordial para su adopción es la interoperabilidad transversal: el 100% de las librerías mencionadas anteriormente (OpenDroneMap, Open3D, Trimesh, OpenCV y YOLO) cuentan con *bindings* nativos o APIs en Python, permitiendo orquestar todo el flujo de trabajo en un único lenguaje. 

● **C++:** El lenguaje descrito por Stroustrup (2013) domina cuando se requiere latencia ultra-baja y control directo sobre la memoria. Aunque motores como Meshroom o CloudCompare están construidos en C++ por criterio de rendimiento en ejecución, el uso directo de C++ en capas de integración y prototipado rápido (*glue code*) suele ser descartado frente a Python debido a que los tiempos de desarrollo y compilación ralentizan el ciclo de validación del software. 

● **Bash / Shell Scripting & Docker:** Como indica Merkel (2014) en su trabajo sobre contenedores Linux ligeros, Docker se ha vuelto indispensable. Su uso, orquestado mediante *scripts* de Shell, se justifica plenamente para aislar el entorno de ejecución. Permite levantar microservicios pesados (como NodeODM) sin contaminar o romper las dependencias del entorno de desarrollo local donde habita la lógica de IA y el *backend* geográfico, asegurando reproducibilidad. 

**6\. Desarrollo de Interfaz y Visualización (Frontend)** 

El último eslabón de la arquitectura tecnológica es la entrega del valor analítico al usuario final a través de una Interfaz Gráfica de Usuario (GUI). El estado del arte actual abarca desde herramientas de prototipado monolíticas hasta arquitecturas web modernas y desacopladas (*Single Page Applications*). Para establecer una base de decisión sólida, se evalúan las siguientes alternativas: 

**6.1. Frameworks de Prototipado Rápido y Escritorio** 

● **Streamlit:** Treuille, Thiery y Bouzbib (2019) diseñaron Streamlit para crear aplicaciones de datos de manera casi instantánea. Su inclusión se justifica por su velocidad de desarrollo iterativo orientado a la web y su soporte nativo para renderizar componentes de datos científicos directamente en el navegador utilizando exclusivamente código Python.  
● **Gradio:** Abid et al. (2019) postulan Gradio bajo una premisa muy similar a Streamlit. Destaca como una alternativa eficiente si el enfoque central recae exclusivamente en probar la inferencia de modelos de Machine Learning (ej. arrastrar una foto de la pila y recibir la imagen segmentada), aunque presenta herramientas menos profundas para la manipulación compleja de *dashboards* multifuncionales. 

● **PyQt / Tkinter:** Representando el paradigma del desarrollo de escritorio (Willman, 2020), librerías como PyQt ofrecen una robustez *offline* absoluta, permitiendo compilar el sistema completo en un archivo ejecutable estático (*.exe*). Este enfoque es valioso para entornos forestales sin conectividad, pero conlleva un desarrollo de interfaz más lento y una mayor complejidad para integrar visualizadores 3D modernos. 

**6.2. Desarrollo Web Moderno (SPA) y Renderizado 3D** 

Para plataformas que requieren escalabilidad corporativa, despliegue en la nube y una experiencia de usuario (UX) interactiva, el estado del arte domina la separación del *backend* de procesamiento lógico respecto del *frontend* visual. 

● **Vue.js:** (You, 2014\) Vue.js destaca por su arquitectura progresiva y su sistema de reactividad eficiente. Su adopción se fundamenta en el balance perfecto entre una curva de aprendizaje moderada y un altísimo rendimiento en la interfaz web. Permite construir *dashboards* dinámicos para la gestión de inventarios de forma muy ágil, operando bajo un paradigma completamente desacoplado del motor de IA. 

● **React.js:** (Meta, 2013\) Como estándar de facto en la industria, React basa su rendimiento en la manipulación del *Virtual DOM*. Su enorme ecosistema facilita la creación de componentes visuales complejos. Su principal desafío frente a otras opciones recae en la necesidad de gestionar meticulosamente el estado global de la aplicación. 

● **Three.js / WebGL:** (Cabello, 2010\) Dado que el núcleo del sistema produce geometrías volumétricas (nubes de puntos y mallas 3D), es imperativo que la interfaz pueda renderizar esta información. Three.js abstrae la complejidad matemática de WebGL, permitiendo incrustar y manipular modelos 3D fluidamente dentro de Vue o React. Esto garantiza interactividad total, permitiendo al operador rotar, hacer zoom y validar visualmente los volúmenes en el navegador sin instalar visores externos. 

La convergencia de estas múltiples tecnologías frontend dentro del estado del arte proporciona las bases necesarias para someterlas a una evaluación multicriterio, en la cual se determinará la arquitectura óptima para las necesidades operativas del software.  
**Matrices de Priorización y Selección Tecnológica** 

**Metodología de Evaluación Ponderada** 

Para determinar la arquitectura de software óptima para el sistema de cuantificación forestal, se ha implementado una matriz de evaluación multicriterio ponderada. 

Cada alternativa tecnológica ha sido puntuada en una escala base del **1 al 5**: 

● **1:** Deficiente / Altamente restrictivo. 

● **2:** Bajo / Presenta limitaciones significativas. 

● **3:** Moderado / Cumple con lo mínimo requerido. 

● **4:** Bueno / Favorable para los objetivos del proyecto. 

● **5:** Excelente / Se alinea perfectamente con los requisitos. 

A cada criterio se le ha asignado un **Peso (%)** que refleja su criticidad estratégica para el éxito del proyecto. La **Puntuación Ponderada** final se calcula multiplicando el puntaje base por su peso correspondiente. El puntaje máximo posible es de **5.00**. 

**1\. Matriz: Motores de Reconstrucción 3D (SfM / MVS)** 

**Justificación de Pesos:** Dado que el proyecto busca democratizar el acceso a la cubicación con bajo costo operativo, el *Costo/Licenciamiento* (30%) y la *Independencia de Hardware* (25%) son los factores más críticos. La precisión pasa a un segundo plano (20%) porque la literatura actual demuestra que la mayoría de los motores logran precisiones forestales aceptables. 

| Criterio de Evaluación | Peso (%) | AliceVision Meshroom | OpenDroneMap (ODM) | MicMac | Agisoft Metashape |
| ----- | ----- | ----- | ----- | ----- | ----- |
| **Costo y Licenciamiento** (Prioridad Open-Source) | 30% | 5 | 5 | 5 | 1 |
| **Independencia de Hardware** (Ejecución en CPU/Sin CUDA) | 25% | 2 | 5 | 4 | 4 |
| **Facilidad de Automatización** (Uso Headless/Docker/API) | 25% | 4 | 5 | 2 | 4 |
| **Precisión Geométrica Forestal** | 20% | 4 | 4 | 5 | 5 |
| **PUNTUACIÓN PONDERADA (Max 5.00)** | **100%** | **3.80** | **4.80** | **4.00** | **3.30** |

**Decisión:** Se selecciona **OpenDroneMap (ODM / NodeODM)**. Al aplicar los pesos, su escalabilidad (Docker) y su independencia de costosas tarjetas gráficas (CUDA) lo posicionan muy por encima de las alternativas, siendo la opción más viable para una arquitectura de bajo costo. 

**2\. Matriz: Librerías de Procesamiento Geométrico** 

**Justificación de Pesos:** La *Capacidad de Cálculo Volumétrico* (35%) es el núcleo del proyecto, seguido de la *API Nativa* (30%) que dictará qué tan rápido se puede programar e integrar la solución. 

| Criterio de Evaluación | Peso (%) | Open3D | CloudCompare | PDAL | Trimesh |
| ----- | ----- | ----- | ----- | ----- | ----- |
| **API Nativa / Facilidad de Integración** | 30% | 5 | 2 | 4 | 5 |
| **Capacidades de Cálculo Volumétrico y Limpieza** | 35% | 5 | 5 | 2 | 4 |
| **Automatización sin Interfaz (Headless)** | 20% | 5 | 3 | 5 | 5 |
| **Curva de Aprendizaje y Documentación** | 15% | 4 | 3 | 3 | 4 |
| **PUNTUACIÓN PONDERADA (Max 5.00)** | **100%** | **4.85** | **3.40** | **3.35** | **4.50** |

**Decisión:** Se selecciona **Open3D**. Su peso en integración y capacidad algorítmica lo hace el claro ganador. Se considerará a **Trimesh** como dependencia secundaria auxiliar para validaciones específicas de mallas triangulares. 

**3\. Matriz: Detección y Segmentación (IA vs. Métodos Clásicos)** 

**Justificación de Pesos:** El entorno forestal es altamente incontrolable. La *Robustez ante ruido* (40%) y la capacidad de hacer *Segmentación de instancias* exacta (35%) son obligatorias para no subestimar el volumen. La eficiencia computacional (10%) es menos relevante porque la inferencia se puede delegar a servidores dedicados. 

| Criterio de Evaluación | Peso (%) | Visión Clásica (OpenCV puro) | Segmentación Deep Learning (YOLOv8) |
| ----- | ----- | ----- | ----- |
| **Robustez ante Ruido y Oclusiones en Madera** | 40% | 2 | 5 |
| **Capacidad de Segmentación de Instancias (Perfil)** | 35% | 2 | 5 |
| **Viabilidad para Automatizar Modelos Diamétricos** | 15% | 1 | 5 |
| **Eficiencia Computacional (Menor consumo)** | 10% | 5 | 3 |
| **PUNTUACIÓN PONDERADA (Max 5.00)** | **100%** | **2.15** | **4.80** |

**Decisión:** Se selecciona **YOLOv8 (Ultralytics)**. La ponderación demuestra que los métodos clásicos colapsan ante la exigencia de exactitud en entornos ruidosos. *(Nota: OpenCV integrará el pipeline exclusivamente para la detección determinista del marco físico de calibración).* 

**4\. Matriz: Lenguaje de Programación y Orquestación** 

**Justificación de Pesos:** Para un proyecto de integración de múltiples motores (IA, 3D, Web), la *Interoperabilidad* (40%) es lo que garantiza que todo el pipeline se pueda comunicar. La *Velocidad de desarrollo* (30%) prioriza llegar rápido a un Producto Mínimo Viable (MVP). 

| Criterio de Evaluación | Peso (%) | Python (3.x) | C++ |
| ----- | ----- | ----- | ----- |
| **Interoperabilidad** (Soporte de ecosistema de librerías) | 40% | 5 | 3 |
| **Velocidad de Desarrollo y Prototipado** | 30% | 5 | 2 |
| **Comunidad y Soporte en Data Science / MLOps** | 20% | 5 | 2 |
| **Rendimiento de Ejecución Cruda** | 10% | 3 | 5 |
| **PUNTUACIÓN PONDERADA (Max 5.00)** | **100%** | **4.80** | **2.70** |

**Decisión:** Se selecciona **Python**. La ponderación castiga fuertemente la lentitud de desarrollo e integración de C++. Python actuará como orquestador general, compensando su menor rendimiento crudo al apoyarse en las librerías precompiladas en C++ (Open3D, NodeODM). 

**5\. Matriz: Desarrollo Web Moderno (Frontend y Renderizado)** 

**Justificación de Pesos:** Para que el usuario valide las mediciones, la *Capacidad de Renderizado 3D* (35%) y una buena *UX/UI* (30%) son vitales para la confianza en el producto. La *Escalabilidad* (25%) define el futuro comercial.

| Criterio de Evaluación | Peso (%) | Streamlit / Gradio (Python UI) | Aplic. Escritorio (PyQt) | SPA (Vue.js / React) \+ Three.js |
| ----- | ----- | ----- | ----- | ----- |
| **Capacidad de Renderizado 3D Interactivo** | 35% | 3 | 2 | 5 |
| **Flexibilidad UX / UI para Usuarios Finales** | 30% | 2 | 3 | 5 |
| **Escalabilidad y Despliegue en la Nube (Comercial)** | 25% | 2 | 2 | 5 |
| **Velocidad Inicial de Prototipado** | 10% | 5 | 3 | 3 |
| **PUNTUACIÓN PONDERADA (Max 5.00)** | **100%** | **2.65** | **2.40** | **4.80** |

**Decisión:** Se selecciona la arquitectura **SPA (Vue.js o React)** complementada con **Three.js**. La ponderación expone la debilidad de herramientas de prototipado rápido como Streamlit cuando se proyectan a un escenario comercial interactivo en la nube.  
**Conclusión de la Selección Arquitectónica Final** 

La aplicación de ponderaciones confirma y refuerza técnica y lógicamente la selección tecnológica. La arquitectura queda formalmente definida por: 

● **Frontend interactivo 3D:** Vue.js / React \+ Three.js. 

● **Motor Backend/API:** Python. 

● **Modelo 3D y Fotogrametría:** OpenDroneMap (NodeODM). 

● **Análisis Geométrico:** Open3D. 

● **IA y Segmentación Visual:** YOLOv8. 

Anexo 

1. Abid, A., Abdalla, A., Abid, A., Khan, D., Alfozan, A., & Zou, J. (2019). Gradio: Hassle-Free Sharing and Testing of ML Models in the Wild. arXiv preprint arXiv:1906.02569.   
2. Araújo Júnior, C. A., & Cordeiro, R. S. R. M. (2025). Assessment of the need for ground control points in aerial surveys for estimating the volume of stacked timber. CERNE, 31, e-103505.   
3. Benassi, F., Dall'Asta, E., Diotri, F., Forlani, G., Morra di Cella, U., Roncella, R., & Santise, M. (2017). UAS photogrammetry without ground control points. The International Archives of the Photogrammetry, Remote Sensing and Spatial Information Sciences, 42, 11-15.   
4. Bradski, G. (2000). The OpenCV Library. Dr. Dobb's Journal of Software Tools, 25(11), 120-123.   
5. Butler, H., et al. (2021). PDAL: Point Data Abstraction Library.   
6. Cabello, R. (2010). Three.js. Repositorio de código abierto.   
7. Dawson-Haggerty, M., et al. (2019). Trimesh. Repositorio de código abierto.   
8. Girardeau-Montaut, D. (2011). CloudCompare. Repositorio de código abierto.   
9. Goycochea Casas, G., et al. (2024). Quantifying solid volume of stacked eucalypt   
   1. timber using detection-segmentation and diameter distribution models. Smart Agricultural Technology, 9, 100653\.   
10. Griwodz, C., Gasparini, S., Calvet, L., Gurdjos, P., Castan, F., Maujean, B., De Lillo, G., & Lanthony, Y. (2021). AliceVision Meshroom: An open-source 3D reconstruction pipeline. En Proceedings of the 12th ACM Multimedia Systems Conference.   
11. Jocher, G., Chaurasia, A., & Qiu, J. (2023). Ultralytics YOLOv8.   
12. Merkel, D. (2014). Docker: lightweight Linux containers for consistent development and deployment. Linux Journal, 2014(239), 2\.   
13. Meta. (2013). React.js. Framework web de código abierto.   
14. Millman, K. J., & Aivazis, M. (2011). Python for Scientists and Engineers. Computing in Science & Engineering, 13(2), 9-12.   
15. Paszke, A., et al. (2019). PyTorch: An Imperative Style, High-Performance Deep Learning Library. En Advances in Neural Information Processing Systems.   
16. Purfürst, F. (2023). Comparison of wood stack volume determination between manual, photo-optical, iPad-LiDAR and handheld-LiDAR based measurement methods. Forest Ecology and Management.  
17. Redmon, J., Divvala, S., Girshick, R., & Farhadi, A. (2016). You Only Look Once: Unified, Real-Time Object Detection. En Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR).   
18. Rupnik, E., Daakir, M., & Pierrot Deseilligny, M. (2017). MicMac – a free, open-source solution for photogrammetry. Open Geospatial Data, Software and Standards, 2(14).   
19. Sona, G., Pinto, L., Pagliari, D., Passoni, D., & Gini, R. (2014). Experimental analysis of different software packages for orientation and digital surface modelling from UAV images. Earth Science Informatics, 7(2), 97-107.   
20. Stroustrup, B. (2013). The C++ Programming Language (4ª ed.). Addison-Wesley Professional.   
21. Toffanin, P. (2019). OpenDroneMap: The Missing Guide. Marlyn Publishing.  
22. Treuille, A., Thiery, T., & Bouzbib, A. (2019). Streamlit.   
23. Ucar, Z., et al. (2024). Evaluating the Use of Smartphone Applications for Log Stacks Volume Measurement in Turkish Forestry Practices. Croatian Journal of Forest Engineering, 45(2), 263-276.   
24. Willman, J. (2020). Modern PyQt: Create GUI Applications for Project Management, Computer Vision, and Data Analysis.   
25. You, E. (2014). Vue.js. Framework web progresivo de código abierto.   
26. Zhou, Q., Park, J., & Koltun, V. (2018). Open3D: A Modern Library for 3D Data Processing. arXiv preprint arXiv:1801.09847.