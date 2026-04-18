# Sistema D3S

Plataforma web interna para gestión de **proyectos**, **contabilidad** y **notificaciones**.

## Stack

- **Backend:** Django 5.2 · Python 3.11
- **Base de datos:** PostgreSQL (producción) · SQLite3 (desarrollo)
- **Servidor:** Gunicorn + WhiteNoise
- **Hosting:** Render (configurado)

## Módulos

| Módulo | Descripción |
|--------|-------------|
| **Economía** | Transacciones, categorías, plan mensual, cierre de caja, tarifas por hora |
| **Proyectos** | Ciclo de vida de proyectos, tareas Kanban, horas de trabajo, facturas |
| **Notificaciones** | Notificaciones internas, integración WhatsApp Cloud API (pendiente) |
| **Core** | Perfil de usuario, seeds iniciales, login/logout |

## Instalación local

```bash
# 1. Clonar y crear entorno virtual
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con los valores reales (mínimo: SECRET_KEY)

# 4. Migrar base de datos
python manage.py migrate

# 5. Cargar datos iniciales (grupos y superusuario)
python manage.py seed_groups

# 6. Correr servidor de desarrollo
python manage.py runserver
```

## Variables de entorno

Ver [.env.example](.env.example) para la lista completa. Las obligatorias son:

- `SECRET_KEY` — clave secreta de Django
- `DATABASE_URL` — cadena de conexión PostgreSQL (vacío usa SQLite)
- `DEBUG` — `1` en desarrollo, `0` en producción

## Tests

```bash
pip install pytest pytest-django
pytest
```

## Roles y permisos

| Permiso | Descripción |
|---------|-------------|
| `economia.can_validate_transactions` | Validar / rechazar transacciones |
| `economia.can_edit_own_transactions` | Editar propias transacciones pendientes |
| `economia.can_delete_own_transactions` | Eliminar propias transacciones pendientes |
| `economia.can_add_ingresos` | Cargar transacciones de tipo ingreso |
| `economia.view_dashboard` | Ver dashboard de economía |
| `proyectos.can_manage_proyectos` | Gestión completa de proyectos |
| `proyectos.can_manage_economia` | Gestión de tarifas y horas |

## Flujo de una transacción

```
Usuario carga transacción (estado: pendiente)
    ↓
Validador revisa en bandeja de pendientes
    ↓
  Aprobar → asigna categoría + proyecto (opcional) → estado: aprobado
  Rechazar → notifica al usuario + elimina la transacción
```

## Flujo de un proyecto

```
Planificado → Presupuestado → Aprobado → En Progreso → Finalizado / Facturación
```

## Despliegue en Render

1. Configurar variables de entorno en el dashboard de Render
2. Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
3. Start command: `gunicorn d3s_system.wsgi`
