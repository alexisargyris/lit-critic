"""
Learning layer for the lit-critic system.
Handles LEARNING.md file persistence and session learning updates.
"""

from datetime import datetime
from pathlib import Path
from .models import LearningData


def load_learning(project_path: Path) -> LearningData:
    """Load existing learning data from LEARNING.md."""
    learning = LearningData()
    filepath = project_path / "LEARNING.md"
    
    if not filepath.exists():
        return learning
    
    content = filepath.read_text(encoding='utf-8')
    
    # Parse the markdown format
    current_section = None
    current_subsection = None
    
    for line in content.split('\n'):
        line = line.strip()
        
        if line.startswith('PROJECT:'):
            learning.project_name = line.split(':', 1)[1].strip()
        elif line.startswith('REVIEW_COUNT:'):
            try:
                learning.review_count = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line == '## Preferences':
            current_section = 'preferences'
        elif line == '## Blind Spots':
            current_section = 'blind_spots'
        elif line == '## Resolutions':
            current_section = 'resolutions'
        elif line == '## Ambiguity Patterns':
            current_section = 'ambiguity'
        elif line == '### Intentional':
            current_subsection = 'intentional'
        elif line == '### Accidental':
            current_subsection = 'accidental'
        elif line.startswith('- ') and current_section:
            entry = {"description": line[2:]}
            if current_section == 'preferences':
                learning.preferences.append(entry)
            elif current_section == 'blind_spots':
                learning.blind_spots.append(entry)
            elif current_section == 'resolutions':
                learning.resolutions.append(entry)
            elif current_section == 'ambiguity':
                if current_subsection == 'intentional':
                    learning.ambiguity_intentional.append(entry)
                elif current_subsection == 'accidental':
                    learning.ambiguity_accidental.append(entry)
    
    return learning


def generate_learning_markdown(learning: LearningData) -> str:
    """Generate LEARNING.md content from learning data."""
    lines = [
        "# Learning",
        "",
        f"PROJECT: {learning.project_name}",
        f"LAST_UPDATED: {datetime.now().strftime('%Y-%m-%d')}",
        f"REVIEW_COUNT: {learning.review_count}",
        "",
        "## Preferences",
        "",
    ]
    
    if learning.preferences:
        for pref in learning.preferences:
            lines.append(f"- {pref.get('description', pref)}")
    else:
        lines.append("[none yet]")
    
    lines.extend([
        "",
        "## Blind Spots",
        "",
    ])
    
    if learning.blind_spots:
        for bs in learning.blind_spots:
            lines.append(f"- {bs.get('description', bs)}")
    else:
        lines.append("[none yet]")
    
    lines.extend([
        "",
        "## Resolutions",
        "",
    ])
    
    if learning.resolutions:
        for res in learning.resolutions:
            lines.append(f"- {res.get('description', res)}")
    else:
        lines.append("[none yet]")
    
    lines.extend([
        "",
        "## Ambiguity Patterns",
        "",
        "### Intentional",
        "",
    ])
    
    if learning.ambiguity_intentional:
        for amb in learning.ambiguity_intentional:
            lines.append(f"- {amb.get('description', amb)}")
    else:
        lines.append("[none yet]")
    
    lines.extend([
        "",
        "### Accidental",
        "",
    ])
    
    if learning.ambiguity_accidental:
        for amb in learning.ambiguity_accidental:
            lines.append(f"- {amb.get('description', amb)}")
    else:
        lines.append("[none yet]")
    
    return '\n'.join(lines)


def save_learning_to_file(learning: LearningData, project_path: Path) -> Path:
    """Save learning data directly to LEARNING.md in the project directory."""
    update_learning_from_session(learning)
    markdown = generate_learning_markdown(learning)
    filepath = project_path / "LEARNING.md"
    filepath.write_text(markdown, encoding='utf-8')
    return filepath


def update_learning_from_session(learning: LearningData) -> None:
    """Process session data into learning entries.
    
    Phase 4 enhancement: Uses explicit preference rules extracted during discussion
    when available, falling back to the original format when not.
    """
    
    # Process rejections -> preferences
    for rejection in learning.session_rejections:
        # Prefer explicit preference rule from discussion (Phase 4: richer learning)
        if rejection.get('preference_rule'):
            desc = f"[{rejection['lens']}] {rejection['preference_rule']}"
        else:
            reason = rejection.get('reason', 'no reason given')
            desc = f"[{rejection['lens']}] {rejection['pattern']} — Author says: \"{reason}\""
        # Check if similar preference already exists
        if not any(desc in p.get('description', '') for p in learning.preferences):
            learning.preferences.append({"description": desc})
    
    # Process acceptances -> potential blind spots (need multiple occurrences)
    # For now, just track them
    for acceptance in learning.session_acceptances:
        desc = f"[{acceptance['lens']}] {acceptance['pattern']}"
        # This would need frequency tracking across sessions
        # For MVP, we'll add after 2+ occurrences
        existing = [bs for bs in learning.blind_spots if acceptance['pattern'] in bs.get('description', '')]
        if not existing:
            # First occurrence, don't add yet but could track
            pass
    
    # Process ambiguity answers
    for answer in learning.session_ambiguity_answers:
        desc = f"{answer['location']}: {answer['description']}"
        if answer['intentional']:
            if not any(desc in a.get('description', '') for a in learning.ambiguity_intentional):
                learning.ambiguity_intentional.append({"description": desc})
        else:
            if not any(desc in a.get('description', '') for a in learning.ambiguity_accidental):
                learning.ambiguity_accidental.append({"description": desc})
    
    # Increment review count
    learning.review_count += 1
