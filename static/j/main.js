function loadingBars() {
    jQuery(".loading-bar").each(function() {
        var text = jQuery(this).html();
        if (text.length < 4) {
            text = text + ".";
        } else {
            text = ".";
        }
        jQuery(this).html(text);
    });
    setTimeout(loadingBars, 500);
}

function reposUl(repos, org) {
    var ul = jQuery("<ul>");
    for(var i = 0; i < repos.length; i += 1) {
        var repo = repos[i];
        var name = repo["name"];
        var description = repo["description"];
        var url;
        if(org) {
            url = "/repo/" + org + "/" + name;
        } else {
            url = "/repo/" + name;
        }
        var li = jQuery("<li>").html("<a href='" + url + "'>" + name + "</a> " + description);
        jQuery(".repos").append(li);
    }
    return ul;
}

function loadUserData() {
    jQuery.ajax({
        url: "/user_data",
        dataType: "json",
        success: function(data) {
            jQuery(".no-user").hide();
            jQuery(".handle").html(data["handle"]);
            jQuery(".repos").html();
            jQuery(".repos").append(reposUl(data["repos"]));
            for(var i = 0; i < data["orgs"].length; i += 1) {
                var org = data["orgs"][i];
                if (org["repos"].length) {
                    jQuery(".repos").append(jQuery("<h3>").html(org["handle"]));
                    jQuery(".repos").append(reposUl(org["repos"], org["handle"]));
                }
            }
            jQuery(".yes-user").show();
        }
    });
}

function loadRepoData() {
    jQuery.ajax({
        url: "/repo_data" + repo_url,
        dataType: "json",
        success: function(data) {
            jQuery(".no-repo").hide();
            jQuery(".repo-members").html();
            for(var i in data) {
                jQuery(".repo-members").append(jQuery("<h3>" + i + "</h3>"));
                for(var j = 0; j < data[i].length; j += 1) {
                    var member = data[i][j];
                    jQuery(".repo-members").append("<p><input type='checkbox' name='userid' value='" + member["id"] + "' checked='checked'> " + member["login"] + " [<a href='http://github.com/" + member["login"] +"'>github</a>]</p>");
                }
            }
            jQuery(".yes-repo").show();
        }
    });
}

jQuery(function() {
    loadingBars();
});
