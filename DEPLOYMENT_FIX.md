# Fix para el error de despliegue en Heroku

## Problema
El archivo `.slugignore` estaba excluyendo `requirements.txt` y `runtime.txt` porque:
- Tenía el patrón `*.txt`
- `.slugignore` **NO soporta negación** (como `!requirements.txt`)

## Solución aplicada
✅ Modificado `.slugignore` para listar archivos específicos en lugar de usar `*.txt`
✅ Ahora `requirements.txt` y `runtime.txt` NO serán excluidos

## Pasos para redesplegar

### 1. Verificar los archivos corregidos
```bash
cd chat_agent_service
git status
```

### 2. Hacer commit de los cambios
```bash
git add .slugignore
git commit -m "Fix: Corregir .slugignore para no excluir requirements.txt"
```

### 3. Redesplegar en Heroku

#### Opción A: Si ya tienes el remote de Heroku configurado
```bash
git push heroku main
```

#### Opción B: Desde el directorio raíz (monorepo)
```bash
cd ..
git add chat_agent_service/.slugignore
git commit -m "Fix: Corregir .slugignore en chat_agent_service"
git subtree push --prefix=chat_agent_service heroku main
```

### 4. Verificar el despliegue
```bash
heroku logs --tail -a chat-agent-service
```

## Verificación
Una vez desplegado, deberías ver:
```
-----> Python app detected
-----> Using Python version specified in runtime.txt
-----> Installing requirements with pip
```

## Lección aprendida
⚠️ **IMPORTANTE**: `.slugignore` es diferente de `.gitignore`
- ❌ NO soporta patrones de negación (`!archivo`)
- ❌ Evitar usar `*.txt` porque excluye archivos críticos
- ✅ Listar archivos específicos a excluir
- ✅ Siempre verificar que `requirements.txt` y `runtime.txt` NO estén excluidos
