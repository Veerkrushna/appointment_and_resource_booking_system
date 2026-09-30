import re

filepath = r"c:\Users\nikhi\OneDrive\Desktop\appointment_and_resource_booking_system\frontend\src\pages\AdminProvidersPage.tsx"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add import
if "ProviderForm" not in content:
    content = content.replace('import AntTimeRangePicker from "../components/AntTimeRangePicker";',
                              'import AntTimeRangePicker from "../components/AntTimeRangePicker";\nimport ProviderForm from "../components/admin/ProviderForm";')

# 2. Remove form states and related refs (lines 40-50 roughly, but we can use regex)
# Be careful not to remove table-related state.
content = re.sub(r'const \[selectedServices, setSelectedServices\] = useState<string\[\]>\(\[\]\);\n\s*const \[showServicesDropdown, setShowServicesDropdown\] = useState\(false\);\n\s*const dropdownRef = useRef<HTMLDivElement>\(null\);\n', '', content)
content = re.sub(r'const \[selectedBlackoutDays, setSelectedBlackoutDays\] = useState<string\[\]>\(\n\s*\[\],\n\s*\);\n\s*const \[showBlackoutDropdown, setShowBlackoutDropdown\] = useState\(false\);\n\s*const blackoutDropdownRef = useRef<HTMLDivElement>\(null\);\n', '', content)

content = re.sub(r'const \[specializationsInput, setSpecializationsInput\] = useState\(""\);\n\s*const \[confirmPassword, setConfirmPassword\] = useState\(""\);\n\s*const \[formData, setFormData\] = useState<ProviderCreate>\({.*?}\);\n\s*const \[formError, setFormError\] = useState<string \| null>\(null\);\n', '', content, flags=re.DOTALL)

# 3. Remove handleClickOutside logic for form dropdowns inside useEffect
handleClickOutsideFormRegex = r'if \(\n\s*dropdownRef\.current &&\n\s*!dropdownRef\.current\.contains\(event\.target as Node\)\n\s*\) \{\n\s*setShowServicesDropdown\(false\);\n\s*\}\n\s*if \(\n\s*blackoutDropdownRef\.current &&\n\s*!blackoutDropdownRef\.current\.contains\(event\.target as Node\)\n\s*\) \{\n\s*setShowBlackoutDropdown\(false\);\n\s*\}'
content = re.sub(handleClickOutsideFormRegex, '', content)

# 4. Remove form helper functions (resetForm, handleInputChange, toggleBlackoutDay, handleSubmit)
# It's safer to remove them block by block using regex or string replacement.
resetFormRegex = r'const resetForm = \(\) => \{.*?\};\n\n'
content = re.sub(resetFormRegex, '', content, flags=re.DOTALL)

handleInputRegex = r'const handleInputChange = \(.*?\};\n\n'
content = re.sub(handleInputRegex, '', content, flags=re.DOTALL)

toggleBlackoutRegex = r'const toggleBlackoutDay = \(day: string\) => \{.*?\};\n\n'
content = re.sub(toggleBlackoutRegex, '', content, flags=re.DOTALL)

handleSubmitRegex = r'const handleSubmit = async \(e: React\.FormEvent\) => \{.*?\};\n\n  const selectedServiceNames = availableServices\n\s*\.filter\(\(s\) => selectedServices\.includes\(s\.id\)\)\n\s*\.map\(\(s\) => s\.name\)\n\s*\.join\(", "\);\n'
content = re.sub(handleSubmitRegex, '', content, flags=re.DOTALL)

# 5. Modify handleEdit to just set editing provider
handleEditRegex = r'const handleEdit = async \(provider: Provider\) => \{.*?window\.scrollTo\(\{ top: 0, behavior: "smooth" \}\);\n\s*\};'
newHandleEdit = '''const handleEdit = async (provider: Provider) => {
    setEditingProviderId(provider.id);
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };'''
content = re.sub(handleEditRegex, newHandleEdit, content, flags=re.DOTALL)


# 6. Replace the JSX form chunk with <ProviderForm>
formJsxRegex = r'\{showForm && \(\n\s*<section\n\s*className="admin-appointments-card"\n\s*style=\{\{ marginBottom: "2rem" \}\}\n\s*>\n\s*<div className="admin-appointments-card__header">\n\s*<h2>\{editingProviderId \? "Edit Provider" : "Add New Provider"\}</h2>\n\s*</div>\n\s*<div className="admin-appointments-card__content">\n\s*<form\n\s*onSubmit=\{handleSubmit\}.*?</section>\n\s*\)\}'

newFormJsx = '''{showForm && (
        <ProviderForm
          token={token}
          provider={editingProviderId ? providers.find((p) => p.id === editingProviderId) || null : null}
          availableServices={availableServices}
          providerServices={editingProviderId && providerServicesMap[editingProviderId] ? 
            availableServices.filter(s => providerServicesMap[editingProviderId].includes(s.name)).map(s => s.id) : []}
          onSubmitSuccess={() => {
            setShowForm(false);
            setEditingProviderId(null);
            loadData();
          }}
          onCancel={() => {
            setShowForm(false);
            setEditingProviderId(null);
          }}
        />
      )}'''

content = re.sub(formJsxRegex, newFormJsx, content, flags=re.DOTALL)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
