Tutorial: Salida Estructurada en JSON con la API de Gemini
La capacidad de generar salida estructurada es una de las capacidades principales (Core Capabilities) de los modelos Gemini. Te permite configurar Gemini para que responda con datos estructurados en lugar de texto sin formato, lo cual es ideal para la extracción precisa y la estandarización de información que luego se puede procesar automáticamente en tus aplicaciones. Por ejemplo, puedes usarla para extraer información de currículums y construir una base de datos estructurada.
Gemini puede generar valores JSON o enum como salida estructurada.
1. Generación de JSON
Para que el modelo genere JSON, debes configurarlo utilizando el parámetro responseSchema. El modelo responderá a cualquier prompt con una salida en formato JSON.
Modelos Compatibles: Modelos como Gemini 1.5 Flash y Gemini 1.5 Pro soportan el modo JSON y el esquema JSON.
Ejemplo en Python (utilizando Pydantic BaseModel)
El SDK de Python de Google GenAI hace que esto sea muy sencillo al permitirte definir el esquema con clases pydantic.BaseModel. El SDK convierte automáticamente tu modelo Pydantic en el esquema JSON correspondiente que la API de Gemini entiende.
Primero, instala pydantic si aún no lo tienes: pip install pydantic.
from google import genai
from pydantic import BaseModel
import json # Para imprimir el resultado de forma legible
import os # Para acceder a tu clave API

# Define tu clave API (asegúrate de que esté configurada como una variable de entorno o de forma segura)
# client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY")) # Si usas variables de entorno
client = genai.Client() # Asume que la clave API ya está configurada o se inicializa de otra forma

# 1. Define el esquema de tu salida JSON usando pydantic.BaseModel
class Recipe(BaseModel):
    recipe_name: str
    ingredients: list[str]

# Puedes definir una lista de este tipo de objetos
# class RecipeList(BaseModel):
#     recipes: list[Recipe] # Si quieres un objeto JSON que contenga una lista de recetas


# 2. Realiza la solicitud al modelo
# Especifica 'application/json' como response_mime_type
# y tu clase Pydantic como response_schema en la configuración (config)
response = client.models.generate_content(
    model="gemini-2.5-flash", # Usa un modelo compatible con Structured Output
    contents="List a few popular cookie recipes, and include the amounts of ingredients.",
    config={
        "response_mime_type": "application/json",
        "response_schema": list[Recipe], # Le indicamos al modelo que esperamos una lista de objetos Recipe
    },
)

# 3. Procesa la respuesta
# La propiedad .parsed del objeto de respuesta contiene los objetos instanciados de Pydantic.
# Si usas una lista como schema, .parsed te devolverá una lista de objetos Recipe.
if response.parsed:
    my_recipes: list[Recipe] = response.parsed
    print("Salida estructurada (objetos Pydantic):")
    for recipe in my_recipes:
        print(f"  Nombre de la receta: {recipe.recipe_name}")
        print(f"  Ingredientes: {', '.join(recipe.ingredients)}")
        print("-" * 20)
else:
    # También puedes acceder al texto sin procesar si .parsed está vacío/nulo
    # Nota: Los validadores de Pydantic aún no son compatibles,
    # por lo que .parsed podría estar vacío/nulo si hay un ValidationError suprimido [65].
    print("Salida de texto sin procesar (si .parsed está vacío):")
    print(response.text)

# Ejemplo de salida JSON (como string, útil para depuración o si .parsed es None)
print("\nSalida JSON sin procesar:")
print(response.text)
Nota: Los validadores de Pydantic aún no son compatibles. Si ocurre un pydantic.ValidationError, este se suprime, y .parsed podría estar vacío o nulo.
Ejemplo en Go (GoLang)
Para Go, debes definir el esquema JSON directamente usando objetos genai.Schema.
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/google/generative-ai-go/genai"
)

func main() {
	ctx := context.Background()
	// Asegúrate de inicializar el cliente con tu clave API
	// client, err := genai.NewClient(ctx, option.WithAPIKey("YOUR_API_KEY")) // Si usas option.WithAPIKey
	client, err := genai.NewClient(ctx, nil) // Asume que la clave API ya está configurada o se inicializa de otra forma
	if err != nil {
		log.Fatal(err)
	}
	defer client.Close()

	// 1. Define el esquema de tu salida JSON usando genai.Schema
	config := &genai.GenerateContentConfig{
		ResponseMIMEType: "application/json",
		ResponseSchema: &genai.Schema{
			Type: genai.TypeArray, // Esperamos una lista de recetas
			Items: &genai.Schema{
				Type: genai.TypeObject,
				Properties: map[string]*genai.Schema{
					"recipeName": {Type: genai.TypeString},
					"ingredients": {
						Type: genai.TypeArray,
						Items: &genai.Schema{Type: genai.TypeString},
					},
				},
				// propertyOrdering es importante para la consistencia [67].
				PropertyOrdering: []string{"recipeName", "ingredients"},
			},
		},
	}

	// 2. Realiza la solicitud al modelo
	model := client.GenerativeModel("gemini-2.5-flash") // Usa un modelo compatible
	resp, err := model.GenerateContent(
		ctx,
		genai.Text("List a few popular cookie recipes, and include the amounts of ingredients."),
		config,
	)
	if err != nil {
		log.Fatal(err)
	}

	// 3. Imprime la respuesta JSON
	fmt.Println(resp.Candidates.Content.Parts.Text)
}
La salida para ambos ejemplos podría verse similar a esto:
[
  {
    "recipeName": "Chocolate Chip Cookies",
    "ingredients": [
      "1 cup (2 sticks) unsalted butter, softened",
      "3/4 cup granulated sugar",
      "3/4 cup packed brown sugar",
      "1 teaspoon vanilla extract",
      "2 large eggs",
      "2 1/4 cups all-purpose flour",
      "1 teaspoon baking soda",
      "1 teaspoon salt",
      "2 cups chocolate chips"
    ]
  },
  ...
]
2. Generación de Valores Enum
En algunos casos, es posible que desees que el modelo elija una sola opción de una lista predefinida de valores. Para esto, puedes pasar un enum en tu esquema. Un enum es un array de strings y se puede usar en cualquier lugar donde se usaría un string en el responseSchema, lo que te permite restringir la salida del modelo para satisfacer los requisitos de tu aplicación.
Ejemplo en Python (utilizando Pydantic BaseModel y enum.Enum)
from google import genai
import enum
from pydantic import BaseModel
import os

client = genai.Client() # Asume que la clave API ya está configurada

# 1. Define tu enumeración
class Grade(enum.Enum):
    A_PLUS = "a+"
    A = "a"
    B = "b"
    C = "c"
    D = "d"
    F = "f"

# 2. Incorpora la enumeración en tu esquema Pydantic
class Recipe(BaseModel):
    recipe_name: str
    rating: Grade # Usamos el enum Grade para la calificación

# 3. Realiza la solicitud al modelo
response = client.models.generate_content(
    model='gemini-2.5-flash', # Usa un modelo compatible
    contents='List 10 home-baked cookie recipes and give them grades based on tastiness.',
    config={
        'response_mime_type': 'application/json',
        'response_schema': list[Recipe], # Esperamos una lista de objetos Recipe
    },
)

# 4. Procesa la respuesta
if response.parsed:
    my_recipes: list[Recipe] = response.parsed
    print("Salida estructurada con enums (objetos Pydantic):")
    for recipe in my_recipes:
        print(f"  Nombre de la receta: {recipe.recipe_name}")
        print(f"  Calificación: {recipe.rating.value}") # Accede al valor del enum
        print("-" * 20)
else:
    print("Salida de texto sin procesar (si .parsed está vacío):")
    print(response.text)
La respuesta podría verse así:
[
  {
    "recipe_name": "Chocolate Chip Cookies",
    "rating": "a+"
  },
  {
    "recipe_name": "Peanut Butter Cookies",
    "rating": "a"
  },
  {
    "recipe_name": "Oatmeal Raisin Cookies",
    "rating": "b"
  },
  ...
]
Ejemplo en REST (para valores Enum directos)
Puedes solicitar un valor enum directamente si la respuesta esperada es una selección simple de una lista.
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent" \
  -H "x-goog-api-key: YOUR_GEMINI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "contents": [{
    "parts":[
    { "text": "What type of instrument is an oboe?" }
    ]
    }],
    "generationConfig": {
    "responseMimeType": "text/x.enum",
    "responseSchema": {
    "type": "STRING",
    "enum": ["Percussion", "String", "Woodwind", "Brass", "Keyboard"]
    }
    }
  }'
3. Acerca de los Esquemas JSON
El parámetro responseSchema se basa en un subconjunto seleccionado del objeto Schema de OpenAPI 3.0, y también añade un campo propertyOrdering.
• propertyOrdering: Cuando trabajas con esquemas JSON en la API de Gemini, el orden de las propiedades es importante. Por defecto, la API ordena las propiedades alfabéticamente y no conserva el orden en que se definen las propiedades (aunque los SDK de Google Gen AI pueden conservar este orden). Si proporcionas ejemplos al modelo con un esquema configurado y el orden de las propiedades de los ejemplos no es consistente con el orden de las propiedades del esquema, la salida podría ser errática o inesperada. Es crucial asegurarse de establecer propertyOrdering[] y de que el orden en tus ejemplos coincida con el esquema.
• Pydantic en Python: Como se mencionó, cuando utilizas un modelo Pydantic, no necesitas trabajar directamente con objetos Schema, ya que el SDK lo convierte automáticamente al esquema JSON correspondiente.
Una representación pseudo-JSON de los campos de Schema incluye: type, format, description, nullable, enum, maxItems, minItems, properties, required, propertyOrdering, e items.
4. Buenas Prácticas y Consideraciones
• Límite de Tokens: El tamaño de tu esquema de respuesta cuenta para el límite de tokens de entrada. Si tienes esquemas muy grandes, esto puede afectar el costo y el rendimiento.
• Campos Opcionales vs. Requeridos: Por defecto, los campos son opcionales, lo que significa que el modelo puede completarlos o omitirlos. Puedes establecer campos como required para forzar al modelo a proporcionar un valor.
• Contexto Suficiente: Si no hay suficiente contexto en el prompt de entrada asociado, el modelo generará respuestas basándose principalmente en los datos con los que fue entrenado, lo que puede resultar en datos genéricos.
• Deshabilitar "Thinking": Para obtener mejores resultados en tareas como la detección de objetos (que a menudo involucran salida estructurada), se recomienda deshabilitar la función de "thinking" estableciendo thinking_budget en 0.
La salida estructurada es una herramienta poderosa para integrar los modelos de Gemini en flujos de trabajo automatizados, transformando respuestas de lenguaje natural en datos procesables para tus aplicaciones.

Tutorial: Llamadas a Funciones (Function Calling) con la API de Gemini
Las llamadas a funciones te permiten conectar los modelos de Gemini con herramientas y APIs externas. En lugar de solo generar respuestas de texto, el modelo puede determinar cuándo necesita usar una función específica y proporcionar los parámetros necesarios para ejecutar acciones en el mundo real. Esto convierte a Gemini en un puente entre el lenguaje natural y las acciones o datos del mundo real.
Casos de Uso Principales:
• Aumentar el conocimiento: Acceder a información de fuentes externas como bases de datos, APIs y bases de conocimiento.
• Ampliar capacidades: Utilizar herramientas externas para realizar cálculos, análisis de datos o simulaciones, superando las limitaciones inherentes del modelo (ej. una calculadora, creación de gráficos).
• Tomar acciones: Interactuar con sistemas externos a través de APIs, como programar citas, enviar correos electrónicos, crear facturas o controlar dispositivos inteligentes.
Modelos de Gemini Compatibles:
Los siguientes modelos de Gemini soportan la llamada a funciones:
• Gemini 2.5 Pro
• Gemini 2.5 Flash
• Gemini 2.5 Flash-Lite
• Gemini 2.0 Flash
• Gemini 2.0 Flash Live
El modelo Gemini 2.0 Flash-Lite no soporta la llamada a funciones.
Preparación: Obtener una Clave API
Necesitarás una clave de API de Gemini. Puedes obtener una en Google AI Studio. Es crucial mantener tu clave de API segura, ya que si se ve comprometida, otros podrían usar tu cuota, incurrir en cargos y acceder a tus datos privados.
Estructura General de una Llamada a Función
El proceso implica definir tus funciones para el modelo, enviar un prompt junto con estas definiciones, y luego manejar la sugerencia de llamada a función que el modelo pueda devolver.
Paso 1: Definir las Declaraciones de tus Funciones
Antes de que Gemini pueda "llamar" a una función, necesitas declararle al modelo qué funciones están disponibles y cómo usarlas. Esto se hace describiendo la función (su nombre, descripción y parámetros) en un formato estructurado.
Ejemplo de declaración de función (Conceptual): Imagina que tienes funciones para controlar las luces de una casa.
# (Este es un ejemplo conceptual de cómo se definirían las funciones en tu código Python
# Las declaraciones reales para Gemini se estructuran un poco diferente como verás en el Paso 2)

def set_light_values_declaration(brightness: float, color: str = "white") -> dict:
    """
    Establece el brillo y el color de las luces inteligentes.

    Args:
        brightness: El nivel de brillo de las luces (0.0 es apagado, 1.0 es encendido total).
        color: El color de las luces. Por defecto es "white".

    Returns:
        Un diccionario con el estado actual de las luces.
    """
    # Aquí iría la lógica para interactuar con tu sistema de luces real
    return {"status": f"Luces ajustadas a {brightness} de brillo y color {color}"}

# Y otras funciones como power_disco_ball, start_music, dim_lights [11-14]
Paso 2: Llamar al Modelo con Declaraciones de Funciones
Una vez que hayas definido las declaraciones de tus funciones, puedes hacer una consulta al modelo. Gemini analizará tu prompt y las declaraciones de las funciones para decidir si debe responder directamente o sugerir una llamada a función.
Ejemplo en Python:
from google import genai
from google.genai import types

# Define la declaración de la función para Gemini
set_light_values_declaration = types.FunctionDeclaration(
    name="set_light_values",
    description="Establece el brillo y el color de las luces inteligentes.",
    parameters={
        "type": "object",
        "properties": {
            "brightness": {"type": "number", "format": "float"},
            "color": {"type": "string", "description": "El color de las luces"}
        },
        "required": ["brightness"]
    }
)

# Configura el cliente y las herramientas
client = genai.Client()
tools = types.Tool(function_declarations=[set_light_values_declaration])
config = types.GenerateContentConfig(tools=[tools])

# Define el prompt del usuario
contents = [
    types.Content(
        role="user",
        parts=[types.Part(text="Baja las luces a un nivel romántico")]
    )
]

# Envía la solicitud con las declaraciones de funciones
response = client.models.generate_content(
    model="gemini-2.5-flash", # Asegúrate de usar un modelo compatible [3, 4]
    contents=contents,
    config=config,
)

# Imprime la sugerencia de llamada a función si existe
print(response.candidates.content.parts.function_call) # [15, 16]
Ejemplo en JavaScript:
import { GoogleGenAI } from '@google/genai';

// Define las declaraciones de las funciones
const setLightValues = {
  name: "set_light_values",
  description: "Establece el brillo y el color de las luces inteligentes.",
  parameters: {
    type: "object",
    properties: {
      brightness: { type: "number", format: "float" },
      color: { type: "string", description: "El color de las luces" }
    },
    required: ["brightness"]
  }
};

const config = {
  tools: [{ functionDeclarations: [setLightValues] }],
};

// Configura el cliente (asegúrate de inicializarlo con tu clave API)
const ai = new GoogleGenAI({ /* apiKey: "YOUR_API_KEY" */ }); // No se muestra en fuente, pero necesario.

async function main() {
  const chat = ai.chats.create({
    model: 'gemini-2.5-flash', // Asegúrate de usar un modelo compatible [3, 4]
    config: config
  });

  const response = await chat.sendMessage({ message: 'Baja las luces a un nivel romántico' });

  // Imprime la sugerencia de llamada a función si existe
  if (response.functionCalls && response.functionCalls.length > 0) {
    console.log(response.functionCalls);
  }
}
main();
Cuando el modelo decide llamar a una función, el objeto de respuesta contendrá una sugerencia de llamada a función.
Paso 3: Ejecutar la Función y Devolver los Resultados (Ciclo de Conversación)
Tu aplicación debe tomar la sugerencia de llamada a función del modelo, ejecutar la función correspondiente en tu backend o sistema externo, y luego enviar los resultados de esa ejecución de vuelta al modelo para que pueda generar una respuesta final para el usuario.
Ejemplo con funciones de fiesta en Python (llamada forzada):
from google import genai
from google.genai import types

# Declaraciones de funciones para Gemini
power_disco_ball_declaration = types.FunctionDeclaration(
    name="power_disco_ball",
    description="Enciende o apaga la bola de discoteca.",
    parameters={"type": "object", "properties": {"power": {"type": "boolean"}}, "required": ["power"]}
)
start_music_declaration = types.FunctionDeclaration(
    name="start_music",
    description="Reproduce música con los parámetros especificados.",
    parameters={
        "type": "object",
        "properties": {
            "energetic": {"type": "boolean", "description": "Si la música es enérgica o no."},
            "loud": {"type": "boolean", "description": "Si la música es fuerte o no."}
        },
        "required": ["energetic", "loud"]
    }
)
dim_lights_declaration = types.FunctionDeclaration(
    name="dim_lights",
    description="Atenúa las luces.",
    parameters={"type": "object", "properties": {"brightness": {"type": "number", "format": "float"}}, "required": ["brightness"]}
)

client = genai.Client()
house_tools = [
    types.Tool(function_declarations=[power_disco_ball_declaration, start_music_declaration, dim_lights_declaration])
]

config = types.GenerateContentConfig(
    tools=house_tools,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True), # Deshabilita la llamada automática para manejar manualmente
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode='ANY') # Fuerza al modelo a llamar a cualquier función [11, 13]
    ),
)

chat = client.chats.create(model="gemini-2.5-flash", config=config)
response = chat.send_message("¡Convierte este lugar en una fiesta!")

print("Ejemplo 1: Llamada a función forzada")
for fn in response.function_calls: # Itera sobre las llamadas a función solicitadas [11, 13]
    args = ", ".join(f"{key}={val}" for key, val in fn.args.items())
    print(f"{fn.name}({args})")

    # Aquí es donde integrarías la lógica real para ejecutar tus funciones
    # Por ejemplo, llamar a una API de smart home o un servicio
    # Y luego, enviar el resultado de la función de vuelta al modelo.
    # En este ejemplo, solo simularemos una respuesta.
    function_result = {"status": "ok"} # Simula el resultado de la ejecución de la función
    chat.send_message(
        types.Part(
            function_response=types.FunctionResponse(
                name=fn.name,
                response=function_result
            )
        )
    )
    # Luego de enviar el resultado, puedes hacer otra solicitud al modelo para obtener su respuesta de texto
    final_response = chat.send_message("¿Qué se siente?")
    print(final_response.text)
Nota: Los resultados impresos reflejan una única llamada a función solicitada por el modelo. Para enviar los resultados de vuelta, inclúyelos en el mismo orden en que fueron solicitados.
Llamada a Función Automática (Solo Python SDK)
El SDK de Python soporta la llamada a función automática, que convierte automáticamente las funciones Python en declaraciones, maneja la ejecución de la llamada a función y el ciclo de respuesta por ti.
Ejemplo en Python con llamada automática:
from google import genai
from google.genai import types

# Implementaciones reales de las funciones
def power_disco_ball_impl(power: bool) -> dict:
    """Powers the spinning disco ball.
    Args:
        power: Whether to turn the disco ball on or off.
    Returns:
        A status dictionary indicating the current state.
    """
    return {"status": f"Disco ball powered {'on' if power else 'off'}"}

def start_music_impl(energetic: bool, loud: bool) -> dict:
    """Play some music matching the specified parameters.
    Args:
        energetic: Whether the music is energetic or not.
        loud: Whether the music is loud or not.
    Returns:
        A dictionary containing the music settings.
    """
    music_type = "energetic" if energetic else "chill"
    volume = "loud" if loud else "quiet"
    return {"music_type": music_type, "volume": volume}

def dim_lights_impl(brightness: float) -> dict:
    """Dim the lights.
    Args:
        brightness: The brightness of the lights, 0.0 is off, 1.0 is full.
    Returns:
        A dictionary containing the new brightness setting.
    """
    return {"brightness": brightness}

# Configura el cliente
client = genai.Client()
config = types.GenerateContentConfig(
    tools=[power_disco_ball_impl, start_music_impl, dim_lights_impl] # Pasa las implementaciones directas
)

# Realiza la solicitud
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="¡Haz todo lo necesario para convertir este lugar en una fiesta!",
    config=config,
)

print("\nEjemplo 2: Llamada a función automática")
print(response.text)
# Salida esperada: "He encendido la bola de discoteca, puesto música fuerte y enérgica, y atenuado las luces al 50% de brillo. ¡Que empiece la fiesta!" [12, 14]
Modos de Llamada a Funciones
La API de Gemini te permite controlar cómo el modelo utiliza las herramientas proporcionadas (declaraciones de funciones) a través del parámetro function_calling_config:
• AUTO (Predeterminado): El modelo decide si generar una respuesta en lenguaje natural o sugerir una llamada a función basándose en el prompt y el contexto. Este es el modo más flexible y recomendado para la mayoría de los escenarios.
• ANY: El modelo está restringido a predecir siempre una llamada a función y garantiza la adherencia al esquema de la función. Si no se especifica allowed_function_names, el modelo puede elegir entre cualquiera de las declaraciones de funciones proporcionadas. Si se proporciona allowed_function_names como una lista, el modelo solo puede elegir entre las funciones de esa lista. Usa este modo cuando requieras una respuesta de llamada a función para cada prompt (si es aplicable).
Integración con Herramientas Nativas
Además de tus funciones personalizadas, Gemini puede utilizar herramientas nativas como:
• Búsqueda de Google (Google Search): Para acceder a información externa y fundamentar respuestas. Por ejemplo, los modelos Live API pueden usar Google Search.
• Ejecución de Código (Code Execution): Para realizar cálculos complejos o análisis de datos. Los modelos Gemini 2.5 Pro, 2.5 Flash, 2.5 Flash-Lite y 2.0 Flash soportan la ejecución de código. No hay cargo adicional por habilitar la ejecución de código, pero se factura por los tokens de entrada y salida.
• Contexto de URL (URL Context): (Característica experimental) Permite proporcionar URLs específicas como contexto adicional para tu prompt. El modelo puede recuperar contenido de esas URLs (si no están detrás de un muro de pago) para informar y dar forma a su respuesta.
Ejemplo de Ejecución de Código en Python (en chat):
from google import genai
from google.genai import types

client = genai.Client()
chat = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        tools=[types.Tool(code_execution=types.ToolCodeExecution)] # Habilita la ejecución de código [82]
    ),
)
response = chat.send_message("Tengo una pregunta de matemáticas para ti.")
print(response.text) # [82]

response = chat.send_message(
    "¿Cuál es la suma de los primeros 50 números primos? "
    "Genera y ejecuta código para el cálculo, y asegúrate de obtener los 50."
)
for part in response.candidates.content.parts:
    if part.text is not None:
        print(part.text)
    if part.executable_code is not None:
        print(part.executable_code.code) # Muestra el código generado por el modelo [82]
    if part.code_execution_result is not None:
        print(part.code_execution_result.output) # Muestra el resultado de la ejecución del código [82]
Mejores Prácticas para Llamadas a Funciones:
• Descripciones de Funciones y Parámetros: Sé extremadamente claro y específico en tus descripciones. El modelo se basa en ellas para elegir la función correcta y proporcionar los argumentos adecuados.
• Nomenclatura: Utiliza nombres de función descriptivos (sin espacios, puntos o guiones).
• Tipado Fuerte: Usa tipos específicos (entero, cadena, enumeración) para los parámetros para reducir errores. Si un parámetro tiene un conjunto limitado de valores válidos, usa una enumeración.
• Selección de Herramientas: Aunque el modelo puede usar un número arbitrario de herramientas, proporcionar demasiadas puede aumentar el riesgo de seleccionar una herramienta incorrecta o subóptima. Para obtener los mejores resultados, intenta proporcionar solo las herramientas relevantes para el contexto o la tarea, idealmente manteniendo el conjunto activo a un máximo de 10-20. Considera la selección dinámica de herramientas basada en el contexto de la conversación si tienes un gran número total de herramientas.
• Ingeniería de Prompts:
    ◦ Proporciona contexto: Dile al modelo su rol (ej., "Eres un asistente meteorológico útil").
    ◦ Da instrucciones: Especifica cómo y cuándo usar las funciones (ej., "No adivines fechas; siempre usa una fecha futura para los pronósticos").
    ◦ Fomenta la clarificación: Instruye al modelo para que haga preguntas aclaratorias si es necesario.
• Temperatura: Utiliza una temperatura baja (ej., 0) para llamadas a funciones más deterministas y fiables.
• Validación: Si una llamada a función tiene consecuencias significativas (ej., realizar un pedido), valida la llamada con el usuario antes de ejecutarla.
• Manejo de Errores: Implementa un manejo de errores robusto en tus funciones para gestionar elegantemente entradas inesperadas o fallos de la API. Devuelve mensajes de error informativos que el modelo pueda usar para generar respuestas útiles al usuario.
• Seguridad: Ten en cuenta la seguridad al llamar a APIs externas. Usa mecanismos de autenticación y autorización adecuados. Evita exponer datos sensibles en las llamadas a funciones.
• Límites de Tokens: Las descripciones y parámetros de las funciones cuentan para tu límite de tokens de entrada. Si alcanzas los límites de tokens, considera limitar el número de funciones o la longitud de las descripciones, o dividir las tareas complejas en conjuntos de funciones más pequeños y enfocados.

utorial: Lectura de Archivos de Imágenes PNG y JSON con la API de Gemini
Los modelos Gemini son multimodales, lo que significa que pueden procesar y comprender varios tipos de datos de entrada, incluyendo texto, imágenes, audio y video. Para interactuar con estos archivos, Gemini ofrece dos métodos principales:
1. Datos en Línea (Inline Data): Para archivos más pequeños (hasta 20 MB en total por solicitud, incluyendo texto e instrucciones).
2. API de Archivos (Files API): Recomendado para archivos más grandes o si planeas reutilizar el archivo en múltiples solicitudes.
Requisitos Previos:
Necesitarás una clave de API de Gemini, que puedes obtener en Google AI Studio. Es crucial mantener tu clave de API segura. Para usar los SDKs, primero instálalos:
• Python: pip install google-generativeai pillow pydantic
• JavaScript/TypeScript: npm install @google/genai
• Go: go get google.golang.org/genai
--------------------------------------------------------------------------------
1. Lectura y Comprensión de Imágenes (PNG)
Los modelos Gemini son multimodales y pueden realizar una amplia gama de tareas de procesamiento de imágenes y visión por computadora, como describir imágenes, responder preguntas visuales, clasificar y detectar objetos.
Formatos de Imagen Soportados: Gemini soporta los tipos MIME image/png, image/jpeg, image/webp, image/heic, y image/heif.
A. Carga de Imágenes PNG como Datos en Línea (Inline Data)
Para archivos PNG pequeños, puedes pasar los datos de la imagen directamente en la solicitud generateContent.
Ejemplo en Python (desde archivo local PNG) [adaptado de 217]
from PIL import Image # Necesitas Pillow para esto
from google import genai
from google.genai import types
import os

# Asume que el cliente ya está configurado con tu clave API
client = genai.Client()

# Ruta a tu archivo PNG local
image_path = 'path/to/your/image.png' # Reemplaza con la ruta real de tu archivo PNG

# Lee el archivo de imagen en bytes
with open(image_path, 'rb') as f:
    image_bytes = f.read()

# Crea el prompt combinando la imagen y texto
response = client.models.generate_content(
    model='gemini-2.5-flash', # Usa un modelo compatible con Image Understanding [10]
    contents=[
        types.Part.from_bytes(
            data=image_bytes,
            mime_type='image/png', # Especifica el tipo MIME correcto [11]
        ),
        'Describe esta imagen.'
    ]
)
print(response.text)
Ejemplo en JavaScript (desde archivo local PNG - Base64) [adaptado de 218]
import { GoogleGenAI } from "@google/genai";
import * as fs from "node:fs";

// Asume que el cliente ya está configurado con tu clave API
const ai = new GoogleGenAI({});

// Ruta a tu archivo PNG local
const imagePath = "path/to/your/image.png"; // Reemplaza con la ruta real de tu archivo PNG

// Lee el archivo de imagen y lo codifica en Base64
const base64ImageFile = fs.readFileSync(imagePath, { encoding: "base64" });

const contents = [
  {
    inlineData: {
      mimeType: "image/png", // Especifica el tipo MIME correcto [11]
      data: base64ImageFile,
    },
  },
  {
    text: "Describe esta imagen.",
  },
];

async function main() {
  const response = await ai.models.generateContent({
    model: "gemini-2.5-flash", // Usa un modelo compatible [10]
    contents: contents,
  });
  console.log(response.text);
}
main();
Ejemplo en Go (desde archivo local PNG) [adaptado de 219]
package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/google/generative-ai-go/genai"
)

func main() {
	ctx := context.Background()
	client, err := genai.NewClient(ctx, nil) // Asume que la clave API está configurada
	if err != nil {
		log.Fatal(err)
	}
	defer client.Close()

	// Ruta a tu archivo PNG local
	imagePath := "path/to/your/image.png" // Reemplaza con la ruta real de tu archivo PNG

	// Lee el archivo de imagen en bytes
	bytes, err := os.ReadFile(imagePath)
	if err != nil {
		log.Fatal(err)
	}

	parts := []*genai.Part{
		genai.NewPartFromBytes(bytes, "image/png"), // Especifica el tipo MIME correcto [11]
		genai.NewPartFromText("Describe esta imagen."),
	}
	contents := []*genai.Content{
		genai.NewContentFromParts(parts, genai.RoleUser),
	}

	result, err := client.Models.GenerateContent(
		ctx,
		"gemini-2.5-flash", // Usa un modelo compatible [10]
		contents,
		nil,
	)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(result.Text())
}
B. Carga de Imágenes PNG usando la API de Archivos (Files API)
Para archivos más grandes o si vas a reutilizar la imagen en múltiples solicitudes, es más eficiente subirla primero con la Files API.
Ejemplo en Python (usando Files API para PNG) [adaptado de 226]
from google import genai
from google.genai import types
import os

client = genai.Client()

# Ruta a tu archivo PNG local
image_path = 'path/to/your/image.png' # Reemplaza con la ruta real de tu archivo PNG

# 1. Sube el archivo usando Files API
# Puedes pasar una ruta o un objeto tipo archivo aquí.
# El MIME type se detecta automáticamente o se puede especificar.
uploaded_file = client.files.upload(
    file=image_path,
    config=types.UploadFileConfig(
        mime_type='image/png' # Especifica el tipo MIME [11]
    )
)
print(f"Archivo subido: {uploaded_file.name} con URI: {uploaded_file.uri}")

# 2. Usa el archivo subido en un prompt
response = client.models.generate_content(
    model="gemini-2.5-flash", # Usa un modelo compatible [10]
    contents=[
        "¿Qué se ve en esta imagen?",
        uploaded_file # Referencia al archivo subido
    ]
)
print(response.text)

# (Opcional) Eliminar el archivo después de usarlo
# client.files.delete(name=uploaded_file.name)
Ejemplo en Go (usando Files API para PNG) [adaptado de 224]
package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/google/generative-ai-go/genai"
)

func main() {
	ctx := context.Background()
	client, err := genai.NewClient(ctx, nil) // Asume que la clave API está configurada
	if err != nil {
		log.Fatal(err)
	}
	defer client.Close()

	// Ruta a tu archivo PNG local
	imagePath := "path/to/your/image.png" // Reemplaza con la ruta real de tu archivo PNG

	// 1. Sube el archivo usando Files API
	uploadedFile, err := client.Files.UploadFromPath(ctx, imagePath, &genai.UploadFileConfig{
		MIMEType: "image/png", // Especifica el tipo MIME correcto [11]
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Archivo subido: %s con URI: %s\n", uploadedFile.Name, uploadedFile.URI)

	// 2. Crea el prompt con el URI del archivo subido
	parts := []*genai.Part{
		genai.NewPartFromText("¿Qué se ve en esta imagen?"),
		genai.NewPartFromURI(uploadedFile.URI, uploadedFile.MIMEType),
	}
	contents := []*genai.Content{
		genai.NewContentFromParts(parts, genai.RoleUser),
	}

	result, err := client.Models.GenerateContent(
		ctx,
		"gemini-2.5-flash", // Usa un modelo compatible [10]
		contents,
		nil,
	)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(result.Text())

	// (Opcional) Eliminar el archivo después de usarlo
	// _, _ = client.Files.Delete(ctx, uploadedFile.Name)
}
C. Entrada de Múltiples Imágenes (incluyendo PNG)
Puedes proporcionar varias imágenes en un solo prompt mezclando datos en línea y referencias a la Files API.
Ejemplo en Python (combinando Files API e Inline Data para imágenes)
from google import genai
from google.genai import types
import os

client = genai.Client()

# 1. Sube la primera imagen (por ejemplo, JPEG) a través de Files API
image1_path = "path/to/image1.jpg" # Reemplaza con la ruta real de tu archivo JPG
uploaded_file = client.files.upload(file=image1_path)

# 2. Prepara la segunda imagen (PNG) como datos en línea
image2_path = "path/to/image2.png" # Reemplaza con la ruta real de tu archivo PNG
with open(image2_path, 'rb') as f:
    img2_bytes = f.read()

# 3. Crea el prompt con texto y múltiples imágenes
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        "¿Qué es diferente entre estas dos imágenes?",
        uploaded_file, # Referencia al archivo subido
        types.Part.from_bytes(
            data=img2_bytes,
            mime_type='image/png' # Datos en línea para la imagen PNG
        )
    ]
)
print(response.text)

# (Opcional) Eliminar el archivo después de usarlo
# client.files.delete(name=uploaded_file.name)
D. Mejores Prácticas para Imágenes
• Imágenes Claras: Usa imágenes claras y no borrosas.
• Orientación Correcta: Verifica que las imágenes estén correctamente rotadas.
• Una Imagen Primero: Cuando uses una sola imagen con texto, coloca la imagen antes del prompt de texto en el array contents para un mejor rendimiento. Para imágenes muy intercaladas con texto, usa el orden más natural.
• Especificidad: Sé específico en tus instrucciones para que el modelo extraiga la información deseada.
--------------------------------------------------------------------------------
2. Lectura de Archivos JSON (como Entrada)
Cuando se trata de leer un archivo JSON como entrada para Gemini, es importante diferenciar entre dos escenarios principales:
1. JSON como archivo de texto para comprensión general: Para el "entendimiento de documentos", Gemini Vision solo entiende PDFs de manera significativa. Otros tipos de documentos como TXT, Markdown, HTML, XML, etc., se extraen como texto puro, perdiendo cualquier especificidad del tipo de archivo, como gráficos, diagramas, etiquetas HTML o formato Markdown. Un archivo JSON caerá en esta categoría si se pasa para una comprensión general del documento.
2. JSON para Ejecución de Código o Modo por Lotes: Aquí es donde los archivos JSON tienen usos más estructurados como entrada.
A. Archivos JSON para Ejecución de Código
El entorno de ejecución de código de Gemini (que soporta Python) puede aceptar archivos de entrada para realizar tareas especializadas. Los tipos de archivos de entrada soportados incluyen .png, .jpeg, .csv, .xml, .cpp, .java, .py, .js, .ts. Aunque JSON no está explícitamente listado con su MIME type, como archivo de texto, puede ser procesado por el código Python generado en el entorno de ejecución.
Ejemplo Conceptual en Python (procesando un JSON con ejecución de código) En este escenario, el modelo generaría código Python para leer y procesar el JSON.
from google import genai
from google.genai import types
import json
import os

client = genai.Client()

# Crea un archivo JSON de ejemplo (simulado)
json_data = {
    "products": [
        {"id": 1, "name": "Laptop", "price": 1200},
        {"id": 2, "name": "Mouse", "price": 25},
        {"id": 3, "name": "Keyboard", "price": 75}
    ]
}
with open("products.json", "w") as f:
    json.dump(json_data, f, indent=2)

# Subir el archivo JSON usando la Files API (recomendado para archivos de entrada)
# Esto lo tratará como 'text/plain' o 'application/json' si se especifica
uploaded_json_file = client.files.upload(file='products.json', config=types.UploadFileConfig(mime_type='application/json'))

prompt = (
    "Tengo un archivo JSON llamado 'products.json' con una lista de productos. "
    "Por favor, calcula el precio total de todos los productos y devuélveme el resultado."
    "Genera y ejecuta el código Python para este cálculo."
)

config = types.GenerateContentConfig(
    tools=[types.Tool(code_execution=types.ToolCodeExecution)] # Habilita la ejecución de código [18, 19]
)

response = client.models.generate_content(
    model="gemini-2.5-flash", # Los modelos Gemini 2.0 y 2.5 soportan ejecución de código [17]
    contents=[prompt, uploaded_json_file], # Pasa el archivo JSON como parte del contenido
    config=config,
)

print("Respuesta del modelo:")
for part in response.candidates.content.parts:
    if part.text is not None:
        print(part.text)
    if part.executable_code is not None:
        print("Código generado:\n", part.executable_code.code)
    if part.code_execution_result is not None:
        print("Resultado de la ejecución:\n", part.code_execution_result.output)

# Limpia el archivo de ejemplo y el archivo subido (opcional)
os.remove("products.json")
client.files.delete(name=uploaded_json_file.name)
En este ejemplo, Gemini leería el archivo JSON a través de la referencia uploaded_json_file, generaría código Python para procesarlo y luego ejecutaría ese código para dar la respuesta.
B. Archivos JSON Lines (JSONL) para Modo por Lotes (Batch Mode)
El Modo por Lotes (Batch Mode) permite enviar múltiples solicitudes GenerateContentRequest de forma asíncrona, y una forma de hacerlo es proporcionando un archivo JSON Lines (JSONL), donde cada línea es un objeto GenerateContentRequest. Dentro de este archivo JSONL, puedes referenciar otros archivos multimedia subidos.
Ejemplo en Python (creando y subiendo un archivo JSONL para Batch Mode)
from google import genai
from google.genai import types
import json
import os

client = genai.Client()

# 1. Crea un archivo JSONL de ejemplo con solicitudes
requests_data = [
    {"key": "request-1", "request": {"contents": [{"parts": [{"text": "Describe el proceso de fotosíntesis."}]}]}},
    {"key": "request-2", "request": {"contents": [{"parts": [{"text": "¿Cuáles son los ingredientes principales de una pizza Margherita?"}]}]}},
    # Puedes incluir referencias a archivos subidos aquí, por ejemplo:
    # {"key": "request-3", "request": {"contents": [{"parts": [{"text": "Describe esta imagen"}, {"file_data": {"mime_type": "image/png", "file_uri": "tu_uri_de_imagen"}}]}]}}
]

with open("my-batch-requests.jsonl", "w") as f:
    for req in requests_data:
        f.write(json.dumps(req) + "\n")

# 2. Sube el archivo JSONL a la Files API
uploaded_file = client.files.upload(
    file='my-batch-requests.jsonl',
    config=types.UploadFileConfig(display_name='my-batch-requests', mime_type='application/jsonl')
)
print(f"Archivo JSONL subido: {uploaded_file.name} con URI: {uploaded_file.uri}")

# (Para ejecutar el trabajo por lotes, necesitarías llamar a la API de procesamiento por lotes con este archivo URI.
# El resultado se devolvería como otro archivo JSONL) [4]

# Limpia el archivo de ejemplo y el archivo subido (opcional)
os.remove("my-batch-requests.jsonl")
client.files.delete(name=uploaded_file.name)
Ejemplo en REST (creando y subiendo un archivo JSONL para Batch Mode)
# 1. Crea un archivo JSONL de ejemplo
echo -e '{"contents": [{"parts": [{"text": "Describe el proceso de fotosíntesis."}]}], "generationConfig": {"temperature": 0.7}}\n{"contents": [{"parts": [{"text": "¿Cuáles son los ingredientes principales de una pizza Margherita?"}]}]}' > my-batch-requests.jsonl

# Define variables de entorno para tu clave API
# export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"

# 2. Sube el archivo JSONL usando la Files API
AUDIO_PATH="my-batch-requests.jsonl"
MIME_TYPE=$(file -b --mime-type "${AUDIO_PATH}") # Debería ser application/jsonl
NUM_BYTES=$(wc -c < "${AUDIO_PATH}")
DISPLAY_NAME="BatchInput"
tmp_header_file="upload-header.tmp"

# Solicitud inicial reanudable para definir metadatos.
# La URL de carga está en los encabezados de respuesta, volcarlos a un archivo.
curl "https://generativelanguage.googleapis.com/upload/v1beta/files" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -D "${tmp_header_file}" \
  -H "X-Goog-Upload-Protocol: resumable" \
  -H "X-Goog-Upload-Command: start" \
  -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
  -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
  -H "Content-Type: application/json" \
  -d "{'file': {'display_name': '${DISPLAY_NAME}'}}" 2> /dev/null

upload_url=$(grep -i "x-goog-upload-url: " "${tmp_header_file}" | cut -d " " -f2 | tr -d "\r")
rm "${tmp_header_file}"

# Sube los bytes reales.
curl "${upload_url}" \
  -H "Content-Length: ${NUM_BYTES}" \
  -H "X-Goog-Upload-Offset: 0" \
  -H "X-Goog-Upload-Command: upload, finalize" \
  --data-binary "@${AUDIO_PATH}" 2> /dev/null > file_info.json

file_uri=$(jq ".file.uri" file_info.json)
echo "URI del archivo JSONL subido: $file_uri"

# (Para ejecutar el trabajo por lotes, necesitarías hacer una solicitud POST a la API de lotes
# referenciando este $file_uri, similar a los ejemplos de Files API para generateContent) [21, 22]

# Limpia los archivos temporales (opcional)
rm my-batch-requests.jsonl file_info.json

## leer datos de storage supabase
Para que FastAPI lea archivos de tu Supabase Storage debes hacerlo desde el servidor usando la clave segura (SUPABASE_SERVICE_ROLE_KEY) o devolviendo una URL firmada al cliente. En el servidor tienes dos patrones comunes:

Redirigir al cliente a una Signed URL (ideal para descarga/visualización directa; baja carga en tu servidor).
Proxy/stream el objeto a través de FastAPI (útil si necesitas controlar acceso, inyectar headers o ocultar la URL real).
A continuación tienes ejemplos para ambos enfoques, más una opción usando el SDK supabase-py.

Opción 1 — Devolver Signed URL (recomendado)
Rápido y escala bien: FastAPI solicita una URL firmada y la devuelve al cliente. El navegador abrirá/descargará el archivo y respectará el Content-Type.

from fastapi import FastAPI, HTTPException
import os
from supabase import create_client  # supabase-py v2

app = FastAPI()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

BUCKET = "portfolio-files"

@app.get("/signed-url/{path:path}")
async def get_signed_url(path: str, expires_in: int = 3600):
    try:
        res = client.storage.from_(BUCKET).create_signed_url(path, expires_in)
        # La estructura dependiente del SDK: adapta si la clave es 'signedURL' o 'signed_url'
        signed_url = res.get("signedURL") or res.get("signed_url")
        if not signed_url:
            raise Exception("No signed URL returned")
        return {"signed_url": signed_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))