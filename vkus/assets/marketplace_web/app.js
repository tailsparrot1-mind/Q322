const $=id=>document.getElementById(id);
const state={role:"",authenticated:false,userId:"",email:"",listings:[],selected:null,editing:null,authMode:"login",category:"Все категории",busy:false};
const icons={"Услуги":"✦","Товары":"◇","Работа":"▣","Подряд и задачи":"⚒","Аренда":"⌂","Покупка":"＋","Продажа":"◆","Другое":"✧"};
const palette=[["#159bd1","#6b49dc"],["#16b8c4","#4265d8"],["#7a42ce","#d64c9f"],["#2860a7","#7351d8"],["#cf579e","#7453cb"]];
function toast(message){const el=$("toast");el.textContent=message;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),2600)}
function show(id){$(id).classList.remove("hidden")}
function hide(id){$(id).classList.add("hidden")}
function esc(value){return String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]))}
function money(item){if(item.price===null||item.price===undefined||item.price==="")return "Цена не указана";const n=Number(item.price);return Number.isFinite(n)?new Intl.NumberFormat("ru-RU",{maximumFractionDigits:0}).format(n)+" "+(item.currency==="USD"?"$":item.currency==="EUR"?"€":"₽"):esc(item.price)}
function art(item,index){return `<div class="card-art art-tone-${index%5}"><span class="kind-badge">${esc(item.kind==="Ищу"?"ИЩУ":"ПРЕДЛАГАЮ")}</span><span class="art-glow"></span><span class="art-icon">${icons[item.category]||"✧"}</span></div>`}
function renderCards(rows){state.listings=rows||[];$("resultCount").textContent=`${state.listings.length} объявлений в выдаче`;const grid=$("listingGrid");if(!state.listings.length){grid.innerHTML='<div class="empty-state"><strong>Пока нет подходящих объявлений</strong><p>Измените фильтры или разместите своё предложение — оно появится здесь после публикации.</p></div>';return}
grid.innerHTML=state.listings.map((item,i)=>`<article class="listing-card" data-id="${esc(item.id)}" tabindex="0" role="button" aria-label="Открыть ${esc(item.title)}">${art(item,i)}<div class="card-body"><div class="card-meta"><span>${esc(item.category||"Объявление")}</span><span>${esc((item.created_at||"").slice(0,10))}</span></div><h3 class="card-title">${esc(item.title)}</h3><p class="card-description">${esc(item.description||"")}</p><div class="card-bottom"><strong class="card-price">${money(item)}</strong><span class="card-city">⌖ ${esc(item.city||"")}</span></div><div class="card-foot"><span>${esc(item.kind==="Ищу"?"Запрос":"Предложение")}</span><span class="card-open">Подробнее ↗</span></div></div></article>`).join("");
grid.querySelectorAll(".listing-card").forEach(card=>{const open=()=>openDetail(card.dataset.id);card.addEventListener("click",open);card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();open()}})})}
function updateAccount(){const logged=state.authenticated;$("accountState").textContent=logged?(state.email||"Вход выполнен"):"Гостевой просмотр";$("avatar").textContent=logged?(state.email||"V").slice(0,1).toUpperCase():"V";$("signOut").classList.toggle("hidden",!logged);$("inboxOpen").classList.toggle("hidden",!logged);$("profileOpen").classList.toggle("hidden",!logged)}
function setCategory(value){state.category=value;document.querySelectorAll(".category-chip").forEach(b=>b.classList.toggle("active",b.dataset.category===value));$("kind").value=$("kind").value;applyFilters()}
async function rpc(name,data={}){return await window.tkwry.invoke(name,data)}
async function bootstrap(){
  try{
    $("connectionState").innerHTML='<i class="live-dot"></i> Подключение к общей базе';
    const result=await rpc("marketplace_bootstrap");
    state.authenticated=!!result.authenticated;
    state.role=result.role||"";
    state.email=result.email||"";
    state.userId=result.user_id||"";
    renderCards(result.listings||[]);
    updateAccount();
    if(result.error){
      $("connectionState").textContent="Ошибка загрузки Marketplace";
      toast(result.error);
    }else{
      $("connectionState").innerHTML='<i class="live-dot"></i> Общая база Vkus · HTTPS';
    }
    if(!state.role){show("roleGate")}else{hide("roleGate")}
  }catch(error){
    $("connectionState").textContent="Нет соединения";
    renderCards([]);
    toast(error.message||"Не удалось загрузить Marketplace");
  }
}
let searchTimer=null;
async function applyFilters(){const query=$("filterSearch").value.trim()||$("search").value.trim();$("resultCount").textContent="Обновляем выдачу…";try{const result=await rpc("marketplace_search",{search:query,kind:$("kind").value,category:state.category,city:$("city").value.trim()});if(result.error)toast(result.error);renderCards(result.listings||[])}catch(error){toast(error.message||"Ошибка поиска")}}
function openAuth(role){state.role=role;state.authMode="login";$("authTitle").textContent="Войти в Marketplace";$("authRoleHint").textContent=role==="Соискатель"?"Роль: ищу товары, услуги и исполнителей":"Роль: размещаю товары, услуги и объявления";$("authError").textContent="";$("authSubmit").textContent="Войти";$("authSwitch").textContent="Нет аккаунта? Зарегистрироваться";hide("roleGate");show("authModal")}
async function submitAuth(){if(state.busy)return;state.busy=true;$("authSubmit").disabled=true;$("authError").textContent="";try{const payload={email:$("authEmail").value.trim(),password:$("authPassword").value,role:state.role};const result=await rpc(state.authMode==="signup"?"marketplace_sign_up":"marketplace_sign_in",payload);if(!result.ok){$("authError").textContent=result.message||"Не удалось выполнить действие";return}if(!result.authenticated){$("authError").textContent=result.message;return}state.authenticated=true;state.role=result.role||state.role;state.email=result.email||payload.email;hide("authModal");hide("roleGate");updateAccount();await bootstrap();toast("Вы вошли в Marketplace")}catch(error){$("authError").textContent=error.message||"Ошибка авторизации"}finally{state.busy=false;$("authSubmit").disabled=false}}
function openListing(item=null){if(!state.authenticated){toast("Войдите в аккаунт, чтобы разместить объявление");openAuth(state.role||"Рекламодатель");return}state.editing=item;$("listingModalTitle").textContent=item?"Редактировать объявление":"Разместить объявление";$("listingKind").value=item?.kind||"Предлагаю";$("listingCategory").value=item?.category||"Услуги";$("listingTitle").value=item?.title||"";$("listingDescription").value=item?.description||"";$("listingCity").value=item?.city||"";$("listingPrice").value=item?.price??"";$("listingCurrency").value=item?.currency||"RUB";$("listingContact").value=item?.contact||"";$("listingError").textContent="";show("listingModal")}
async function saveListing(){const payload={kind:$("listingKind").value,category:$("listingCategory").value,title:$("listingTitle").value.trim(),description:$("listingDescription").value.trim(),city:$("listingCity").value.trim(),price:$("listingPrice").value.trim(),currency:$("listingCurrency").value,contact:$("listingContact").value.trim()};try{const result=state.editing?await rpc("marketplace_update_listing",{listing_id:state.editing.id,payload}):await rpc("marketplace_create_listing",{payload});if(!result.ok){$("listingError").textContent=result.message||"Не удалось сохранить";return}hide("listingModal");toast("Объявление сохранено");await applyFilters()}catch(error){$("listingError").textContent=error.message||"Ошибка сохранения"}}
function openDetail(id){const item=state.listings.find(row=>String(row.id)===String(id));if(!item)return;state.selected=item;const i=state.listings.indexOf(item);$("detailContent").innerHTML=`${art(item,i)}<p class="eyebrow">${esc(item.category)} · ${esc(item.kind)}</p><h2>${esc(item.title)}</h2><div class="detail-price">${money(item)}</div><p class="detail-description">${esc(item.description)}</p><p class="muted">⌖ ${esc(item.city)} · ${esc((item.created_at||"").slice(0,16).replace("T"," "))}</p>`;const own=state.authenticated&&String(item.owner_id)===String(state.userId);let actions='';if(own){actions+='<button class="button button-blue" id="editOwn">Редактировать</button><button class="button button-quiet" id="deleteOwn">Удалить</button>'}else{actions+='<button class="button button-pink" id="respondButton">Откликнуться</button>'}$("detailActions").innerHTML=actions;if($("editOwn"))$("editOwn").onclick=()=>{hide("detailModal");openListing(item)};if($("deleteOwn"))$("deleteOwn").onclick=deleteSelected;if($("respondButton"))$("respondButton").onclick=respondSelected;show("detailModal")}
async function deleteSelected(){if(!state.selected||!confirm("Удалить это объявление?"))return;const result=await rpc("marketplace_delete_listing",{listing_id:state.selected.id});if(!result.ok){toast(result.message);return}hide("detailModal");toast("Объявление удалено");await applyFilters()}
async function respondSelected(){if(!state.authenticated){hide("detailModal");openAuth("Соискатель");return}const message=prompt("Напишите сообщение автору (до 2000 символов):");if(message===null)return;const result=await rpc("marketplace_respond",{listing_id:state.selected.id,message});if(!result.ok){toast(result.message);return}toast("Отклик отправлен")}
async function openProfile(){if(!state.authenticated){openAuth(state.role||"Соискатель");return}const result=await rpc("marketplace_get_profile");if(!result.ok){toast(result.message);return}$("profileName").value=result.profile.display_name||state.email;$("profileCity").value=result.profile.city||"";$("profileError").textContent="";show("profileModal")}
async function saveProfile(){const result=await rpc("marketplace_save_profile",{display_name:$("profileName").value.trim(),city:$("profileCity").value.trim()});if(!result.ok){$("profileError").textContent=result.message;return}hide("profileModal");toast("Профиль сохранён")}
async function openInbox(){const result=await rpc("marketplace_inbox");if(!result.ok){toast(result.message);return}const list=$("inboxList");if(!result.responses.length){list.innerHTML='<div class="empty-state"><strong>Пока нет откликов</strong><p>Когда пользователи ответят на ваши объявления, сообщения появятся здесь.</p></div>'}else{list.innerHTML=result.responses.map(row=>`<article class="inbox-item"><strong>${esc(row.listing_title||"Объявление")}</strong><p>${esc(row.message)}</p><small>${esc(row.status)} · ${esc(row.created_at||"")}</small><div class="detail-actions"><button class="button button-quiet" data-response="${esc(row.id)}" data-status="Просмотрен">Просмотрен</button><button class="button button-blue" data-response="${esc(row.id)}" data-status="Принят">Принять</button><button class="button button-quiet" data-response="${esc(row.id)}" data-status="Отклонён">Отклонить</button></div></article>`).join("");list.querySelectorAll("[data-response]").forEach(button=>button.onclick=async()=>{const updated=await rpc("marketplace_update_response",{response_id:button.dataset.response,status:button.dataset.status});if(!updated.ok)toast(updated.message);else openInbox()})}show("inboxModal")}
function resetFilters(){ $("filterSearch").value="";$("search").value="";$("kind").value="Все типы";$("city").value="";setCategory("Все категории")}
document.querySelectorAll("[data-role]").forEach(button=>button.addEventListener("click",()=>openAuth(button.dataset.role)));
$("continueGuest").onclick=()=>hide("roleGate");
$("authSubmit").onclick=submitAuth;$("authSwitch").onclick=()=>{state.authMode=state.authMode==="login"?"signup":"login";$("authTitle").textContent=state.authMode==="signup"?"Создать аккаунт":"Войти в Marketplace";$("authSubmit").textContent=state.authMode==="signup"?"Зарегистрироваться":"Войти";$("authSwitch").textContent=state.authMode==="signup"?"Уже есть аккаунт? Войти":"Нет аккаунта? Зарегистрироваться"};
$("authBack").onclick=()=>{hide("authModal");show("roleGate")};
document.querySelectorAll("[data-close]").forEach(button=>button.onclick=()=>hide(button.dataset.close));
$("publishButton").onclick=()=>openListing();$("listingSave").onclick=saveListing;$("profileOpen").onclick=openProfile;$("profileSave").onclick=saveProfile;$("inboxOpen").onclick=openInbox;
$("searchGo").onclick=applyFilters;$("applyFilters").onclick=applyFilters;$("resetFilters").onclick=resetFilters;$("filterSearch").addEventListener("keydown",e=>{if(e.key==="Enter")applyFilters()});$("search").addEventListener("keydown",e=>{if(e.key==="Enter")applyFilters()});
$("categoryNav").querySelectorAll("[data-category]").forEach(button=>button.onclick=()=>setCategory(button.dataset.category));
$("signOut").onclick=async()=>{const result=await rpc("marketplace_sign_out");if(!result.ok){toast(result.message);return}state.authenticated=false;state.role="";state.email="";state.userId="";updateAccount();show("roleGate");toast("Вы вышли из аккаунта")};
$("sortButton").onclick=()=>toast("Сначала новые — сортировка по дате публикации");
function scheduleBootstrap(){
  const start=()=>window.setTimeout(()=>bootstrap(),250);
  if(document.readyState==="complete")start();
  else window.addEventListener("load",start,{once:true});
}
scheduleBootstrap();
