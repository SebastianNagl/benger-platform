# BenGER User Guide v2

This comprehensive guide covers all user roles in the BenGER platform: administrators, annotators, and contributors.

# Administrator Handbook

This handbook provides a comprehensive overview of the administrative functions of the BenGER platform for administrators.

## Administrator Role

As an administrator, you have full access to all functions of the BenGER platform, including:

- User management
- Role assignment
- System configuration
- Task management
- Data upload and management
- Evaluation control

## User Management

### Creating Users

1. Navigate to **Admin → Users** in the main menu
2. Click the **New User** button
3. Fill out the form with the following information:
   - Email address
   - Name
   - Assigned role (Superadmin, Org Admin, Contributor, Annotator, User)
4. Click **Save**

### Changing User Roles

1. Navigate to **Admin → Users** in the main menu
2. Find the corresponding user in the list
3. Click **Edit**
4. Change the role in the dropdown menu
5. Click **Save**

### Deactivating Users

1. Navigate to **Admin → Users** in the main menu
2. Find the corresponding user in the list
3. Click **Deactivate**
4. Confirm the action in the confirmation dialog

## Organization Management

### Creating Organizations

1. Navigate to **Organizations** in the main menu
2. Click **New Organization**
3. Fill out the form:
   - Name: Full organization name
   - Slug: Short identifier (e.g., "tum")
   - Description: Optional description
4. Click **Create**

### Adding Users to Organizations

1. Navigate to **Organizations**
2. Select an organization
3. Click **Manage Users**
4. Add users and assign roles:
   - Enter email address
   - Choose organization role (Org Admin, Org Contributor, Org User)
   - Optional: Adjust global role
5. Click **Add**

### Tasks and Organizations

Tasks are automatically linked with organizations:
- **Default**: Creator organization + TUM (always included)
- **Additional Organizations**: Can be assigned by superadmins and TUM users
- **Visibility**: Only users from assigned organizations can see the task

### Editing Organizations

1. Navigate to **Organizations**
2. Click on the organization name
3. Edit name, description, or settings
4. Click **Save**

## System Administration

### Monitoring System Status

The dashboard in the administration area provides an overview of the current system status:

- Active users
- Running tasks
- System utilization
- Recent errors
- Memory usage

### Managing API Keys

For integrating external services, you can generate and manage API keys:

1. Navigate to **Admin → API Configuration**
2. Click **New API Key**
3. Select the access scope for the key
4. Note the generated key (it will only be displayed once)

## Task Management

As an administrator, you can view, edit, and delete all tasks in the system, regardless of who created them.

### Managing Task Visibility

BenGER implements a comprehensive visibility system:

#### **Visibility Levels**
- **Public Tasks**: Accessible to all authenticated users
- **Private Tasks**: Only accessible to users of assigned organizations

#### **Administrator Rights**
- Superadmins can manage all tasks regardless of visibility or organization
- Full access for platform administration and oversight

#### **Default Settings**
- New tasks are created as private by default
- TUM organization is automatically assigned
- Synchronized tasks from enterprise systems are private

### Viewing All Tasks

1. Navigate to **Admin → Tasks**
2. Here you see a list of all tasks in the system with filtering options
3. **Visibility Filter**: Filter by public or private tasks
4. **Organization Filter**: Show tasks from specific organizations

### Editing Tasks

1. Select a task from the list
2. Click **Edit**
3. Modify the following properties:
   - **Visibility**: Switch between public and private
   - **Organizations**: Edit organization assignments
   - **Other Properties**: Name, description, template, etc.
4. Click **Save**

### Changing Task Visibility

1. Open the task for editing
2. **Set Public**: Makes the task visible to all users
3. **Set Private**: Restricts access to assigned organizations
4. **Adjust Organizations**: For private tasks, check organization assignments

### Deleting Tasks

1. Select a task from the list
2. Click **Delete**
3. Confirm the deletion in the confirmation dialog

## Native Annotation System

The BenGER platform includes a comprehensive native annotation system for annotation tasks.

### Accessing Annotation Management

1. Navigate to **Admin → Annotations**
2. Access the annotation project management interface

### Managing Annotation Projects

1. Create new annotation projects directly in BenGER
2. Configure the annotation interface using built-in templates
3. Assign annotators with role-based access
4. Monitor annotation progress with real-time analytics

## LLM Evaluation

### Starting a New Evaluation

1. Navigate to **Admin → Benchmark**
2. Select the task to be evaluated
3. Select the model to be evaluated
4. Configure the evaluation parameters
5. Click **Start Evaluation**

### Viewing Evaluation Results

1. Navigate to **Admin → Benchmark**
2. Select the **Results** tab
3. Filter by task or model
4. Click on an evaluation to view details

## Backup and Maintenance

### Database Backup

1. Navigate to **Admin → System → Backup**
2. Click **Create Backup**
3. Select the data to be backed up
4. Click **Start Backup**

### System Maintenance

Schedule regular maintenance work:

1. Navigate to **Admin → System → Maintenance**
2. Schedule a maintenance window
3. Configure user notifications
4. Click **Activate Maintenance Mode**

# Annotator Handbook

This handbook provides comprehensive guidance for annotators on the BenGER platform. As an annotator, you play an important role in creating high-quality training data for benchmarks in the German legal domain.

## Your Role as Annotator

As an annotator, you have the following tasks and permissions:

- Annotate documents according to given guidelines
- Access to assigned annotation tasks
- View your annotation statistics and quality
- Provide feedback on annotation guidelines

## Getting Started

### Login and Dashboard

1. Log in to the BenGER platform with your credentials
2. After login, you will be redirected to the dashboard
3. On the dashboard you can see:
   - Your open annotation tasks
   - Recently edited documents
   - Your annotation statistics
   - Notifications about new tasks

### Finding Documents for Annotation

There are two main ways to find your annotation tasks:

1. **Via the Dashboard**:
   - Click on the displayed open tasks
   - Or click "Show All Tasks"

2. **Via the Main Menu**:
   - Navigate to "Documents"
   - Here you see all documents assigned to you
   - Use the filter functions to search for specific documents

## Annotation Process

### Dokument öffnen

1. Wählen Sie ein Dokument aus Ihrer Liste
2. Klicken Sie auf "Annotieren"
3. Das Dokument wird im Native Annotation System-Interface geöffnet
4. Lesen Sie sich vor Beginn der Annotation die Richtlinien durch (Zugänglich über den "Richtlinien"-Button)

### Performing Annotation

The annotation process differs depending on the task type:

#### Klassifikation

1. Lesen Sie das gesamte Dokument
2. Wählen Sie die passende Kategorie aus den vorgegebenen Optionen
3. Fügen Sie bei Bedarf Kommentare hinzu
4. Klicken Sie auf "Speichern"

#### Entitätsextraktion

1. Lesen Sie das Dokument
2. Markieren Sie relevante Textpassagen mit der Maus
3. Wählen Sie den entsprechenden Entitätstyp aus dem erscheinenden Menü
4. Wiederholen Sie diesen Vorgang für alle zu annotierenden Entitäten
5. Klicken Sie auf "Speichern"

#### Frage-Antwort

1. Lesen Sie das Dokument und die zugehörige Frage
2. Markieren Sie die Textpassage, die die Antwort enthält
3. Klicken Sie auf "Antwort markieren"
4. Bei Fragen ohne direkte Antwort im Text wählen Sie "Keine Antwort möglich"
5. Klicken Sie auf "Speichern"

### Completing Annotation

After annotation, you have the following options:

1. **Save**: Saves your current progress, you can continue later
2. **Submit**: Completes the annotation and marks the document as finished
3. **Reject**: If a document cannot be annotated (e.g., wrong language, incomplete text)
   - Select "Reject"
   - Provide a reason for rejection
   - Click "Confirm"

## Annotation Guidelines

Each annotation task is based on specific guidelines that must be followed:

### Accessing Guidelines

1. During annotation: Click the "Guidelines" button in the Native Annotation System interface
2. Before annotation: Open the "Guidelines" tab in the task overview

### Umgang mit Grenzfällen

Bei unklaren oder nicht eindeutigen Fällen:

1. Konsultieren Sie die Richtlinien und suchen Sie nach ähnlichen Beispielen
2. Verwenden Sie die Kommentarfunktion, um Ihre Entscheidung zu erläutern
3. Bei grundsätzlichen Unklarheiten: Wenden Sie sich an den Task-Ersteller

## Quality Assurance

### Your Annotation Quality

The quality of your annotations is regularly checked:

1. By comparison with reference annotations
2. By agreement with other annotators (Inter-Annotator Agreement)
3. By spot checks from contributors or administrators

### Feedback zu Ihren Annotationen

1. Navigieren Sie zu "Mein Profil" → "Annotationsstatistik"
2. Hier finden Sie:
   - Anzahl der annotierten Dokumente
   - Ihre Annotationsqualität
   - Erhaltenes Feedback
   - Verbesserungsvorschläge

## Tips for Efficient Annotation

1. **Read guidelines carefully**: Familiarize yourself with the guidelines before starting.
2. **Maintain consistency**: Apply the same criteria to all documents.
3. **Take regular breaks**: Take breaks to maintain concentration.
4. **Time management**: Plan sufficient time for each document.
5. **Provide feedback**: Report unclear guidelines or problems.

## Häufige Fragen

### Tastaturkürzel

Um Ihre Annotationsarbeit zu beschleunigen, können Sie folgende Tastaturkürzel verwenden:

- **S**: Speichern
- **D**: Nächstes Dokument
- **A**: Vorheriges Dokument
- **E**: Bearbeitung aktivieren
- **Esc**: Aktuelle Aktion abbrechen

### Problembehebung

- **Interface lädt nicht**: Aktualisieren Sie die Seite und prüfen Sie Ihre Internetverbindung.
- **Annotation wird nicht gespeichert**: Prüfen Sie, ob alle erforderlichen Felder ausgefüllt sind.
- **Dokument wird falsch angezeigt**: Melden Sie das Problem mit der Schaltfläche "Problem melden".

Bei technischen Schwierigkeiten oder Fragen zum Annotationsprozess wenden Sie sich an den Task-Ersteller oder die Plattformadministratoren über die Kontaktfunktion. # Contributor Handbook

This handbook provides comprehensive guidance for contributor users of the BenGER platform. As a contributor, you have the ability to create benchmark tasks, manage data, and evaluate LLMs.

## Your Role as Contributor

As a contributor, you have the following permissions and responsibilities:

- Create and manage benchmark tasks
- Upload and categorize legal documents
- Define annotation guidelines
- Evaluate models and analyze results
- Participate in annotation processes

## Task Management

### Creating a New Task

1. Navigate to **Tasks** in the main menu
2. Click **Create New Task**
3. Fill out the form with the following information:
   - **Task Name**: A concise title for the task
   - **Description**: Detailed explanation of the task
   - **Task Type**: Select the appropriate type (Classification, Extraction, etc.)
   - **Visibility**: 
     - **Private (recommended)**: Only visible to organization members
     - **Public**: Visible to all platform users
   - **Organizations**: Automatically assigned (your organizations + TUM)
4. Click **Create**

#### **Visibility Recommendations**
- **Private Tasks** for sensitive or proprietary research data
- **Public Tasks** for open research collaborations and public datasets
- **Default**: New tasks are private to ensure data privacy

### Task-Template definieren

Nach der Erstellung des Tasks können Sie das Annotations-Template definieren:

1. Öffnen Sie den erstellten Task
2. Navigieren Sie zum Tab **Template**
3. Verwenden Sie die Native Annotation System-Konfigurationssprache, um das Template zu erstellen
4. Hier ein Beispiel für ein Klassifikationstemplate:

```xml
<View>
  <Text name="text" value="$text"/>
  <Choices name="type" toName="text" choice="single">
    <Choice value="Kaufvertrag"/>
    <Choice value="Mietvertrag"/>
    <Choice value="Dienstvertrag"/>
    <Choice value="Werkvertrag"/>
    <Choice value="Sonstiger Vertrag"/>
  </Choices>
</View>
```

5. Klicken Sie auf **Speichern**

### Dokumente hinzufügen

Um Dokumente zu einem Task hinzuzufügen:

1. Öffnen Sie den gewünschten Task
2. Navigieren Sie zum Tab **Dokumente**
3. Klicken Sie auf **Dokumente hinzufügen**
4. Laden Sie Dokumente hoch (unterstützte Formate: PDF, DOCX, TXT)
5. Weisen Sie optional Metadaten zu (z.B. Kategorie, Jahr, Quelle)

### Annotationsrichtlinien erstellen

Detaillierte Richtlinien helfen Annotatoren, konsistente Ergebnisse zu erzielen:

1. Öffnen Sie den Task
2. Navigieren Sie zum Tab **Richtlinien**
3. Klicken Sie auf **Bearbeiten**
4. Verfassen Sie klare Anweisungen:
   - Ziel der Annotation
   - Regeln und Kriterien
   - Beispiele für korrekte und inkorrekte Annotationen
   - Umgang mit Grenzfällen
5. Klicken Sie auf **Speichern**

## Data Management

### Uploading Documents

1. Navigate to **Data** in the main menu
2. Click **Upload Documents**
3. Select the task the documents should belong to
4. Drag files to the upload area or click **Select Files**
5. Click **Upload** to start the process

### Dokumente verwalten

1. Navigieren Sie zu **Daten → Dokumente**
2. Hier finden Sie eine Übersicht aller hochgeladenen Dokumente
3. Nutzen Sie die Filterfunktionen, um spezifische Dokumente zu finden
4. Sie können Dokumente:
   - Betrachten
   - Metadaten bearbeiten
   - Löschen
   - Zwischen Tasks verschieben

## Annotation

Als Contributor können Sie selbst Annotationen durchführen:

1. Navigieren Sie zu **Tasks → [Ihr Task] → Dokumente**
2. Klicken Sie auf **Annotieren** neben einem Dokument
3. Die Native Annotation System-Oberfläche wird geöffnet
4. Führen Sie die Annotation gemäß den Richtlinien durch
5. Klicken Sie auf **Speichern** oder **Absenden**

### Annotationsfortschritt überwachen

1. Navigieren Sie zu **Tasks → [Ihr Task]**
2. Im Dashboard sehen Sie den aktuellen Annotationsfortschritt
3. Überprüfen Sie die Qualität der Annotationen durch:
   - Stichprobenartige Kontrollen
   - Übereinstimmungsmetriken bei mehrfach annotierten Dokumenten

## LLM Evaluation

### Starting Evaluation

1. Navigate to **Evaluation**
2. Select the task to be evaluated
3. Select the model to be evaluated (e.g., GPT-4, Claude, etc.)
4. Select the relevant metrics (Accuracy, F1-Score, etc.)
5. Click **Start Evaluation**

### Ergebnisse analysieren

Nach Abschluss der Evaluation:

1. Navigieren Sie zu **Evaluation → Ergebnisse**
2. Wählen Sie die gewünschte Evaluation aus
3. Untersuchen Sie die Leistung anhand verschiedener Metriken
4. Vergleichen Sie verschiedene Modelle miteinander
5. Exportieren Sie Ergebnisse für weitere Analysen

## Best Practices for Contributors

1. **Clear Annotation Guidelines**: Create detailed and unambiguous guidelines.
2. **Regular Quality Control**: Spot-check annotation quality regularly.
3. **Consistent Task Design**: Ensure uniform task design and structure.
4. **Balanced Data**: Ensure your documents are representative and balanced.
5. **Documentation**: Document all decisions and task specifics in writing.

## Problembehebung

### Common Problems and Solutions

- **Document upload fails**: Check the file format and file size.
- **Template errors**: Verify the XML syntax in the Native Annotation System template.
- **Annotation problems**: Ensure all annotation types are correctly configured.

For technical problems you cannot solve yourself, contact the administrator team. 
