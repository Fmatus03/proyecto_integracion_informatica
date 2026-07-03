# Diseno de bateria cientifica

Cada auditoria se plantea con objetivo, hipotesis, procedimiento, metricas, visualizaciones y criterio.

| Auditoria | Objetivo | Hipotesis | Procedimiento | Metricas | Visualizaciones | Criterio |
|---|---|---|---|---|---|---|
| Inventario | Saber que evidencia existe. | Si faltan tracks/depth de la ultima sesion, no se puede probar soporte por camara. | Buscar artefactos ODM/OpenSfM existentes. | conteo, ruta, utilidad | CSV/JSON | Aceptar solo afirmaciones soportadas por archivos presentes. |
| Soporte fotogrametrico | Medir observaciones por punto. | Regiones espurias tendrian bajo numero de vistas o mala geometria angular. | Reproyectar puntos usando poses/tracks/depth de la misma corrida. | n camaras, angulo base, reprojection residual | heatmaps por region | Rechazar si soporte comparable al core; aceptar si soporte significativamente menor. |
| Cobertura visual | Detectar zonas ocluidas o mal vistas. | Superficies espurias nacen donde hay pocas vistas utiles. | Calcular visibilidad/cobertura angular por punto. | solid angle, baseline, redundancia | overlays de cobertura | Aceptar si contactos tienen cobertura baja vs core. |
| Densidad | Comparar soporte local. | Geometria espuria tiene densidad distinta o baja. | KDTree local r=0.20 y kdist20. | vecinos, kdist | histogramas/PLY | Aceptar diferencia si medianas/percentiles se separan claramente. |
| Normales | Medir coherencia superficial. | Interpolaciones tendran normales mas coherentes/laminares o inconsistentes segun ruido. | Estimar normales y abs(dot) local. | normal consistency | histograma | Clasificar segun diferencia vs core. |
| Curvatura | Buscar superficies suavizadas/puentes. | Interpolacion crea curvatura baja o transiciones suaves no cilindricas. | PCA local. | curvatura lambda_min/sum | histograma/overlay | Aceptar evidencia si contactos difieren del core. |
| Espesor | Detectar laminas artificiales. | Superficies interpoladas tienen espesor p05-p95 bajo y alta planitud. | PCA por crop de contacto. | thickness, planarity | PLY por region | Aceptar evidencia si espesor/planitud difiere del core. |
| Depth/MVS | Aislar si nace en mapas de profundidad. | Si depth maps ya contienen la superficie, origen es MVS. | Comparar depth maps originales contra nube densa. | residuales profundidad, consistencia multi-vista | overlays por imagen | Bloqueado sin depth maps de la misma corrida. |
