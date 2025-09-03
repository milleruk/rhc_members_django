#!/bin/bash
# save as commit.sh and chmod +x commit.sh

# Step 1: Update requirements.txt
pip freeze > requirements.txt

# Step 2: Stage all changes
git add .

# Step 3: Ask for commit message
read -p "Enter commit message: " msg
git commit -m "$msg"

# Step 4: Ask if we want to push
read -p "Do you want to push to origin/main? (y/N): " confirm
if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
    git push -u origin main
else
    echo "Changes committed locally but not pushed."
fi
