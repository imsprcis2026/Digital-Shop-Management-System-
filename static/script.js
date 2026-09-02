function toggleMenu(){
  const panel=document.getElementById("menu-panel");
  if(panel) panel.classList.toggle("show");
}

function toggleSettings(){
  const panel=document.getElementById("settings-panel");
  if(panel) panel.classList.toggle("show");
}

function toggleColorDropdown(event){
  event.stopPropagation();
  const menu=document.getElementById("theme-dropdown-menu");
  if(menu) menu.classList.toggle("show");
}

document.addEventListener("click", function(event){
  const menu=document.getElementById("theme-dropdown-menu");
  if(menu && !event.target.closest(".theme-dropdown")) menu.classList.remove("show");
});

function toggleRowActions(event, button){
  event.stopPropagation();
  const current = button.closest(".row-actions");
  document.querySelectorAll(".row-actions.open").forEach(item=>{
    if(item !== current) item.classList.remove("open");
  });
  current?.classList.toggle("open");
}

function confirmDelete(message){
  return window.confirm(message || "Are you sure?");
}

function previewLogo(input){
  const file=input.files && input.files[0];
  const preview=document.getElementById("logo-preview");
  const empty=document.getElementById("logo-empty");
  const name=document.getElementById("logo-name");
  if(!file) return;
  if(name) name.textContent=file.name;
  if(preview){
    preview.src=URL.createObjectURL(file);
    preview.style.display="block";
  }
  if(empty) empty.style.display="none";
}

function toggleCustomUnit(){
  const select=document.getElementById("stock-unit");
  const box=document.getElementById("custom-unit-box");
  if(!select || !box) return;
  box.classList.toggle("show", select.value === "Custom");
}

function bindSaleRow(row){
  const select=row.querySelector(".item-select");
  if(!select) return;
  select.addEventListener("change", function(){ setRowPrice(row); });
  row.querySelector(".qty-input")?.addEventListener("input", calcSaleTotal);
}

function setRowPrice(row){
  const select=row.querySelector(".item-select");
  const unit=row.querySelector(".unit-output");
  const price=row.querySelector(".price-input");
  const option=select?.selectedOptions[0];
  if(unit) unit.value=option?.dataset.unit || "";
  if(price) price.value=option?.dataset.price || "";
  calcSaleTotal();
}

function addSaleRow(){
  const container=document.getElementById("sale-items");
  const first=container?.querySelector(".row-item");
  if(!container || !first) return;
  const row=first.cloneNode(true);
  row.querySelectorAll("input").forEach(input=>{
    if(input.classList.contains("line-total")) input.value="0.00";
    else input.value="";
  });
  row.querySelector("select").selectedIndex=0;
  row.querySelector(".remove-item")?.addEventListener("click", function(){ removeSaleRow(this); });
  bindSaleRow(row);
  container.appendChild(row);
  calcSaleTotal();
}

function removeSaleRow(button){
  const rows=document.querySelectorAll("#sale-items .row-item");
  if(rows.length <= 1){
    button.closest(".row-item")?.querySelector("select")?.focus();
    return;
  }
  button.closest(".row-item")?.remove();
  calcSaleTotal();
}

function calcSaleTotal(){
  let total=0;
  document.querySelectorAll("#sale-items .row-item").forEach(row=>{
    const qty=parseFloat(row.querySelector(".qty-input")?.value || 0);
    const price=parseFloat(row.querySelector(".price-input")?.value || 0);
    const line=qty*price;
    total+=line;
    const output=row.querySelector(".line-total");
    if(output) output.value=line.toFixed(2);
  });
  const grand=document.getElementById("grand-total");
  if(grand) grand.value=total.toFixed(2);
  const paid=parseFloat(document.getElementById("paid")?.value || 0);
  const remaining=document.getElementById("remaining");
  if(remaining) remaining.value=Math.max(total-paid,0).toFixed(2);
}

function setDeviceTime(){
  const now=new Date();
  const date=now.getFullYear()+"-"+String(now.getMonth()+1).padStart(2,"0")+"-"+String(now.getDate()).padStart(2,"0");
  let hour=now.getHours();
  const minute=String(now.getMinutes()).padStart(2,"0");
  const suffix=hour>=12 ? "PM" : "AM";
  hour=hour%12 || 12;
  const time=String(hour).padStart(2,"0")+":"+minute+" "+suffix;
  const dateField=document.getElementById("device-date");
  const timeField=document.getElementById("device-time");
  if(dateField) dateField.value=date;
  if(timeField) timeField.value=time;
}

function toggleChangePassword(){
  const box=document.getElementById("change-password");
  const button=document.getElementById("change-password-toggle");
  if(!box) return;
  const open=box.hasAttribute("hidden");
  if(open){
    box.removeAttribute("hidden");
    button?.setAttribute("aria-expanded","true");
    setTimeout(()=>box.scrollIntoView({behavior:"smooth",block:"nearest"}),60);
  }else{
    box.setAttribute("hidden","");
    button?.setAttribute("aria-expanded","false");
  }
}

window.addEventListener("load",function(){
  setDeviceTime();
  toggleCustomUnit();
  document.querySelectorAll("#sale-items .row-item").forEach(bindSaleRow);
  calcSaleTotal();
});



document.addEventListener("click", function(event){
  if(!event.target.closest(".row-actions")){
    document.querySelectorAll(".row-actions.open").forEach(item=>item.classList.remove("open"));
  }
});


// ============================================================
// LANGUAGE SYSTEM
// The selected language is stored by Flask. The bill area is deliberately
// excluded so every bill and printable bill stays in English.
// ============================================================
const hinglishDictionary = {
  "Dashboard":"Dashboard", "Back":"Wapas", "Back to Dashboard":"Dashboard par wapas",
  "Settings":"Settings", "Profile":"Profile", "Logout":"Logout", "Delete Account":"Account Delete",
  "Light Theme":"Light Theme", "Dark Theme":"Dark Theme", "Color Theme":"Color Theme", "Language":"Language",
  "Add Stock":"Stock Add Karein", "View Stock":"Stock Dekhein", "Add Sale":"Sale Add Karein", "View Sales":"Sales Dekhein",
  "Payment History":"Payment History", "Customer History":"Customer History", "Purchase History":"Purchase History",
  "Save Stock":"Stock Save Karein", "Update Stock":"Stock Update Karein", "Save Payment":"Payment Save Karein",
  "Search":"Search Karein", "Today's Sales":"Aaj ki Sales", "Pending Payments":"Pending Payments",
  "Stock Report":"Stock Report", "Sales Report":"Sales Report", "Open Report":"Report Kholein",
  "Customer Name":"Customer ka Naam", "Customer Contact":"Customer Contact", "Supplier Name":"Supplier ka Naam",
  "Supplier Contact":"Supplier Contact", "Item Name *":"Item ka Naam *", "Quantity *":"Quantity *",
  "Buying Price (per unit)":"Buying Price (per unit)", "Selling Price (per unit)":"Selling Price (per unit)",
  "Low Stock Limit":"Low Stock Limit", "Grand Total":"Grand Total", "Paid Amount":"Paid Amount",
  "Remaining Amount":"Remaining Amount", "Items":"Items", "Item":"Item", "Unit":"Unit", "Qty":"Qty",
  "Price":"Price", "Total":"Total", "Edit":"Edit Karein", "Delete":"Delete Karein", "Pay":"Payment Karein",
  "Return":"Return Karein", "Print Bill":"Bill Print Karein", "Login Account":"Account Login Karein",
  "Create a New Account":"Naya Account Banayein", "Account":"Account", "Choose Date":"Date Chunein"
};

function canTranslateElement(el){
  if(!el || el.closest('.billbox, .notranslate, .language-setting, .auth-language-bar')) return false;
  if(el.closest('tbody') && !el.matches('.empty')) return false; // never translate saved/user data
  if(el.closest('.welcome') && el.querySelector('b')) return false; // preserve shop name
  if(el.matches('option')) return false;
  return true;
}

function getTranslatableElements(){
  const selector='h1,h2,h3,h4,label,button,a,small,th,.desc,.empty,.form-title,.menu-heading,.brand,.alert b,.report-summary span,.status-badge,.muted-note';
  return [...document.querySelectorAll(selector)].filter(canTranslateElement).filter(el=>{
    const t=el.textContent.trim();
    return t && t.length<=180 && !el.querySelector('input,select,textarea');
  });
}

function translateHinglish(elements){
  elements.forEach(el=>{
    const raw=el.textContent.trim();
    if(hinglishDictionary[raw]) el.textContent=hinglishDictionary[raw];
  });
  document.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el=>{
    if(!canTranslateElement(el)) return;
    const raw=el.getAttribute('placeholder');
    if(hinglishDictionary[raw]) el.setAttribute('placeholder',hinglishDictionary[raw]);
  });
}

async function applySelectedLanguage(){
  const body=document.body;
  if(!body) return;
  const language=body.dataset.selectedLanguage || 'en';
  document.documentElement.lang=language==='hinglish' ? 'en' : language;
  if(language==='en') return;

  const elements=getTranslatableElements();
  if(language==='hinglish'){
    translateHinglish(elements);
    return;
  }

  // Translate only fixed interface text. Saved names, item names and table data stay unchanged.
  const texts=elements.map(el=>el.textContent.trim());
  const placeholders=[...document.querySelectorAll('input[placeholder],textarea[placeholder]')]
    .filter(canTranslateElement).map(el=>({el,text:el.getAttribute('placeholder')}));
  const all=[...texts,...placeholders.map(x=>x.text)].filter(Boolean);
  if(!all.length) return;

  try{
    const response=await fetch('/translate-ui',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({language:language,texts:all})
    });
    const data=await response.json();
    const translated=data.translations || [];
    let i=0;
    elements.forEach(el=>{ const value=translated[i++]; if(value) el.textContent=value; });
    placeholders.forEach(item=>{ const value=translated[i++]; if(value) item.el.setAttribute('placeholder',value); });
  }catch(error){
    // If the device is offline, the selected language remains saved and English UI stays usable.
    console.warn('Language translation unavailable:', error);
  }
}

window.addEventListener('DOMContentLoaded', applySelectedLanguage);
