import re

filepath = r"c:\Users\nikhi\OneDrive\Desktop\appointment_and_resource_booking_system\frontend\src\pages\AdminProvidersPage.tsx"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Remove the leftover form states that regex didn't catch because of formatting
content = re.sub(r'const \[showForm, setShowForm\] = useState\(false\);\n.*?const \[formError, setFormError\] = useState<string \| null>\(null\);', 
                 'const [showForm, setShowForm] = useState(false);', 
                 content, flags=re.DOTALL)

# Remove leftover handleSubmit logic if any (from `if (!formData.type) {` to `setFormError(err.message);\n    }\n  };\n`)
content = re.sub(r'const handleSubmit = async \(e: React.FormEvent\) => \{.*?\};\n', '', content, flags=re.DOTALL)

# Let's catch anything looking like form handlers that were missed. 
# In the previous step, resetForm, handleInputChange, toggleBlackoutDay were mostly removed? 
# Wait, let me check if they exist.
content = re.sub(r'const resetForm = \(\) => \{.*?\};\n\n', '', content, flags=re.DOTALL)
content = re.sub(r'const handleInputChange = \(.*?\) => \{.*?\};\n\n', '', content, flags=re.DOTALL)

# Fix the Add Provider / Cancel button logic which referenced `resetForm`
content = re.sub(r'onClick=\{\(\) => \{\n\s*if \(showForm\) \{\n\s*setShowForm\(false\);\n\s*setEditingProviderId\(null\);\n\s*resetForm\(\);\n\s*\} else \{\n\s*setEditingProviderId\(null\);\n\s*resetForm\(\);\n\s*setShowForm\(true\);\n\s*\}\n\s*\}\}', 
                 '''onClick={() => {
            if (showForm) {
              setShowForm(false);
              setEditingProviderId(null);
            } else {
              setEditingProviderId(null);
              setShowForm(true);
            }
          }}''', content)

# Check if handleSubmit was completely chopped. The previous regex missed it because it didn't match the signature properly or there was no matching end brace.
# Let's just aggressively remove any leftover `handleSubmit` string from `if (!formData.type)` to `};\n` before `handleDeactivate`
leftover_submit_match = re.search(r'(if \(!formData\.type\).*?)const handleDeactivate =', content, flags=re.DOTALL)
if leftover_submit_match:
    content = content.replace(leftover_submit_match.group(1), '')

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
